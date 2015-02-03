# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2013-2015 Martin Altmayer, Michael Helmling
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import collections

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt
translate = QtCore.QCoreApplication.translate

from . import coverbrowser, selection
from ..core import nodes, covers, levels, elements, tags


class CoverTable(coverbrowser.AbstractCoverWidget):
    """Standard display class for coverbrowser.CoverBrowser. It uses a QGraphicsView to draw covers in a
    table layout."""
    def __init__(self, state, coverBrowser):
        super().__init__(coverBrowser)
        layout = QtGui.QHBoxLayout(self)
        self.view = QtGui.QGraphicsView(CoverTableScene(self, coverBrowser.worker,
                                                        state.get('size') if state is not None else 80))
        self.view.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.view.setDragMode(QtGui.QGraphicsView.ScrollHandDrag)
        self.view.scene().selectionChanged.connect(self.selectionChanged)
        layout.addWidget(self.view)

    @classmethod
    def getTitle(cls):
        return translate("CoverBrowser", "Table")
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Bugfix: Calling _handleResize directly does not work if the CoverBrowser is hidden at startup.
        # When it is shown, resizeEvent is called before self.view.vieport.size() is updated.
        QtCore.QTimer.singleShot(0, self.view.scene()._handleResize)
        
    def setCovers(self, ids, coverPaths):
        self.view.scene().setCovers(ids, coverPaths)
        
    def getCoverSize(self):
        return self.view.scene().getCoverSize()
    
    def setCoverSize(self, size):
        self.view.scene().setCoverSize(size)
        
    def selection(self):
        return self.view.scene().selection()
    
    def createConfigWidget(self, parent):
        widget = QtGui.QWidget(parent)
        layout = QtGui.QFormLayout(widget)
        
        sizeSliderLayout = QtGui.QHBoxLayout()
        sizeSlider = QtGui.QSlider(Qt.Horizontal) 
        sizeSlider.setMinimum(20)
        sizeSlider.setMaximum(200)
        sizeSlider.setValue(self.getCoverSize())
        sizeSlider.valueChanged.connect(self.setCoverSize)
        sizeSliderLayout.addWidget(sizeSlider)
        sizeLabel = QtGui.QLabel(str(self.getCoverSize()))
        sizeSlider.valueChanged.connect(lambda x: sizeLabel.setText(str(x)))
        sizeSliderLayout.addWidget(sizeLabel)
        layout.addRow(self.tr("Cover size: "), sizeSliderLayout)
        return widget
    
    def state(self):
        return {'size': self.getCoverSize()}

coverbrowser.addDisplayClass('table', CoverTable)

    
class CoverTableScene(QtGui.QGraphicsScene):
    """QGraphicsScene that contains one CoverItem for each cover and arranges them in a grid."""
    innerSpaceFactor = 3./8. # fraction of coverSize that is used as inner space
    shadowFactor = 1./15. # fraction of coverSize that is used for shadows
    outerSpace = 15 # constant outer space
    
    def __init__(self, parent, worker, size):
        super().__init__(parent)
        self.worker = worker
        self.columnCount = 0
        
        self.coverItems = {}
        self._setCoverSize(size)
        covers.addCacheSize(self.coverSize)
        
        self.loadingPixmap = QtGui.QPixmap(':maestro/process-working.png')
        self.loadingTimer = QtCore.QTimer(self)
        self.loadingTimer.setInterval(50) # Timer for loading animation
        self.reloadCoverTimer = QtCore.QTimer(self)
        self.reloadCoverTimer.setSingleShot(True)
        self.reloadCoverTimer.setInterval(1000)
        self.reloadCoverTimer.timeout.connect(self._handleReloadCoverTimer)

    def setCovers(self, ids, coverPaths):
        """Set the covers that are displayed. *ids* is a list of elements-ids (which can be used to fetch
        information besides covers, e.g. for tooltips). *coverPaths* is a dict mapping ids to the cover path
        (relative to the cover directory). Covers should be displayed in the order specified by *ids*."""
        self.loadingTimer.stop()
        self.clear()
        self.coverItems = collections.OrderedDict((id, CoverItem(self, id, coverPaths[id])) for id in ids)
        for item in self.coverItems.values():
            self.addItem(item)
        self.arrange()
        self.loadingTimer.start()
        
    def arrange(self):
        """Move all covers (CoverItems) to their place in the grid."""
        self.columnCount = self._computeColumnCount()
        
        row = column = 0
        for item in self.coverItems.values():
            item.setPos(self._getPos(row, column))
            column += 1
            if column == self.columnCount:
                column = 0
                row += 1
        totalRows = row+1 if column != 0 else row
        totalColumns = min(self.columnCount, len(self.coverItems))
        self.setSceneRect(0, 0,
                      2*self.outerSpace + totalColumns * (self.coverSize+self.innerSpace) - self.innerSpace,
                      2*self.outerSpace + totalRows * (self.coverSize+self.innerSpace) - self.innerSpace)
                
    def _getPos(self, row, column):
        """Transform row/column coordinates to pixel coordinates: Return the position of the top-left corner
        of the cover at the given row and column in pixels."""
        x = self.outerSpace + column * (self.coverSize + self.innerSpace)
        y = self.outerSpace + row * (self.coverSize + self.innerSpace)
        return QtCore.QPointF(x,y)
    
    def _handleResize(self):
        """React to resize events of the view."""
        if self.columnCount != self._computeColumnCount():
            self.arrange()
            
    def _computeColumnCount(self):
        """Return the number of columns (which depends on the viewport size."""
        availableWidth = self.views()[0].viewport().width() - 2*self.outerSpace
        return max(1, (availableWidth+self.innerSpace) // (self.coverSize+self.innerSpace))
    
    def _handleReloadCoverTimer(self):
        covers.addCacheSize(self.coverSize)
        for item in self.coverItems.values():
            item.reload()
        
    def getCoverSize(self):
        """Return the current cover size as int (covers are always drawn quadratically)."""
        return self.coverSize
    
    def setCoverSize(self, size):
        """Set the current cover size to size x size (covers are always drawn quadratically)."""
        assert size is not None
        if size != self.coverSize:
            self._setCoverSize(size)
            self.arrange()
            self.reloadCoverTimer.start()
        for item in self.coverItems.values():
            item.update()
            
    def _setCoverSize(self, size):
        """Set or initialize cover size and variables depending on it."""
        self.coverSize = size
        self.innerSpace = int(self.innerSpaceFactor * size)
        newShadowOffset = int(round(self.shadowFactor * size))
        if not hasattr(self,'shadowOffset') or newShadowOffset != self.shadowOffset:
            self.shadowOffset = newShadowOffset
            for item in self.coverItems.values():
                if item.graphicsEffect() is not None:
                    item.graphicsEffect().setOffset(newShadowOffset)
            
    def selection(self):
        """Return a selection.Selection object based on the selected covers."""
        return selection.Selection.fromElements(levels.real,
                                    levels.real.collect([item.elid for item in self.selectedItems()]))
        
    def helpEvent(self, helpEvent):
        # Note: Setting all tooltips when the scene is generated takes much too long. Reimplementing
        # QGraphicsItem.toolTip does not work for some reason. Thus we reimplement the code that displays
        # tooltips.
        item = self.itemAt(helpEvent.scenePos())
        if item is not None:
            QtGui.QToolTip.showText(helpEvent.screenPos(), self._createToolTip(item))
        helpEvent.accept()
            
    def _createToolTip(self, item, coverSize=150, showTags=True, showFlags=False, showParents=True):
        """Create a tool tip for the given CoverItem."""
        #TODO: merge with RootedTreeModel.createWrapperToolTip
        el = levels.real[item.elid]
        lines = [el.getTitle()]
        if el.isFile() and el.url is not None:
            lines.append(str(el.url))
        elif el.isContainer():
            lines.append(el.type.title())
        if showTags and el.tags is not None:
            lines.extend("{}: {}".format(tag.title, ', '.join(map(str, values)))
                         for tag, values in el.tags.items() if tag != tags.TITLE)
        
        if showFlags and el.tags is not None and len(el.flags) > 0:
            lines.append(translate("RootedTreeModel", "Flags: ")+','.join(flag.name for flag in el.flags))
            
        if showParents and el.parents is not None:
            parentIds = list(el.parents)
            parents = levels.real.collect(parentIds)
            parents.sort(key=elements.Element.getTitle)
            lines.extend(translate("RootedTreeModel", "#{} in {}").format(p.contents.positionOf(el.id),
                                                                          p.getTitle())
                         for p in parents)
        
        # Escape tags for use in HTML
        import html
        lines = '<br/>'.join(html.escape(line) for line in lines)
        
        if coverSize is not None and el.hasCover():
            imgTag = el.getCoverHTML(coverSize, 'style="float: left"')
            return imgTag + '<div style="margin-left: {}">{}</div>'.format(coverSize+5, lines)
        else:
            # enclose in a div so that Qt formats this as rich text.
            # Otherwise HTML escapes would be printed as plain text.
            return '<div>{}</div>'.format(lines)


class CoverItem(QtGui.QGraphicsItem):
    """A GraphicsItem which draws either a cover and a dropshadow or a loading animation."""
    def __init__(self, scene, elid, path):
        super().__init__()
        self.scene = scene
        self.elid = elid
        self.frame = 1 # frame of the loading animation
        self.cover = None
        self._oldCover = None
        self.setCoverPath(path)
        
    def setCoverPath(self, path):
        """Set the cover displayed in this CoverItem. *path* must point to the original (large) cover, not
        to a smaller cached version. Until the cover is loaded the old cover is displayed if available.
        Otherwise a loading animation will be shown.
        """
        self.path = path
        if self.cover is not None and self.cover.loaded:
            self._oldCover = self.cover
        self.cover = covers.LoadCoverTask(path, self.scene.coverSize)
        self.scene.worker.submit(self.cover)
        if not self.cover.loaded:
            self.scene.loadingTimer.timeout.connect(self._handleTimer)
        else: self._addShadow()
        self.setFlag(QtGui.QGraphicsItem.ItemIsSelectable)
    
    def reload(self):
        """Reload the cover from source."""
        self.setCoverPath(self.path)
        
    def _handleTimer(self):
        """React to the scene's loading timer: Move loading animation to the next frame."""
        if self.cover.loaded:
            self.scene.loadingTimer.timeout.disconnect(self._handleTimer)
            self._addShadow()
            self._oldCover = None
        else:
            self.frame += 1
            if self.frame >= 32:
                self.frame = 1
        self.update()
        
    def _addShadow(self):
        """Add a shadow to the item. The shadow should be added when the image is loaded, so that the
        loading animation is drawn without a shadow."""
        if self.graphicsEffect() is None:
            effect = QtGui.QGraphicsDropShadowEffect()
            effect.setOffset(5)
            self.setGraphicsEffect(effect)
        
    def boundingRect(self):
        return QtCore.QRectF(0, 0, self.scene.coverSize+2, self.scene.coverSize+2)
    
    def paint(self, painter, option, widget):
        size = self.scene.coverSize
        if self.cover.loaded or self._oldCover is not None:
            # Find pixmap to draw
            if self.cover.loaded:
                if not self.cover.pixmap.isNull():
                    pixmap = self.cover.pixmap
                else: pixmap = QtGui.QPixmap(':maestro/cover_missing.png')
            else: pixmap = self._oldCover.pixmap

            # Scale correctly
            w, h = pixmap.width(), pixmap.height()
            if w == h:
                painter.drawPixmap(1, 1, size, size, pixmap)
                borderRect = QtCore.QRect(0, 0, size+1, size+1)
            elif w > h:
                height = int(size/w * h)
                offset = int((size-height) / 2) 
                painter.drawPixmap(1, 1 + offset, size, height, pixmap)
                borderRect = QtCore.QRect(0, offset, size+1, height+1)
            else:
                width = int(size/h * w)
                offset = int((size-width) / 2)
                painter.drawPixmap(1 + offset, 1, width, size, pixmap)
                borderRect = QtCore.QRect(offset, 0, width+1, size+1)
        else:
            if self.scene.coverSize >= 32:
                destXY = (self.scene.coverSize-32) // 2 + 1 # +1: adjust for border
                destSize = 32
            else:
                destXY = 0
                destSize = self.scene.coverSize
            srcX = 32 * (self.frame % 8)
            srcY = 32 * (self.frame // 8)
            painter.drawPixmap(destXY, destXY, destSize, destSize,
                               self.scene.loadingPixmap,
                               srcX, srcY, 32, 32)
            borderRect = QtCore.QRect(0, 0, size+1, size+1)
        pen = painter.pen()
        if option.state & QtGui.QStyle.State_Selected:
            pen.setColor(QtGui.QColor(0,0,255))
        else: pen.setColor(QtGui.QColor(0,0,0))
        painter.setPen(pen)
        painter.drawRect(borderRect)

    def mouseMoveEvent(self, event):
        if QtCore.QLineF(QtCore.QLine(event.screenPos(), event.buttonDownScreenPos(Qt.LeftButton))).length() \
                > QtGui.QApplication.startDragDistance():
            drag = QtGui.QDrag(event.widget())
            sel = self.scene.selection()
            drag.setMimeData(selection.MimeData(sel))
            if len(sel.wrappers()) == 1:
                drag.setPixmap(sel.wrappers()[0].element.getCover(100))
                drag.setHotSpot(QtCore.QPoint(50, 50))
            drag.exec_()
            self.setCursor(Qt.OpenHandCursor)
            
    def mouseDoubleClickEvent(self, event):
        wrapper = nodes.Wrapper(levels.real.collect(self.elid))
        wrapper.loadContents(recursive=True)
        from . import playlist
        playlist.appendToDefaultPlaylist([wrapper], replace=event.modifiers() & Qt.ControlModifier)
        