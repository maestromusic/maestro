# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2015 Martin Altmayer, Michael Helmling
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

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
translate = QtCore.QCoreApplication.translate

from maestro import config, utils
from maestro.gui import mainwindow, selection
from maestro.core import levels, covers, tags, elements


class CoverDesk(mainwindow.Widget):
    def __init__(self, state=None, **args):
        super().__init__(**args)
        self.hasOptionDialog = True
        layout = QtWidgets.QHBoxLayout(self)
        scene = CoverDeskScene(self)
        
        if state is not None:
            if 'elements' in state:
                levels.real.collect([elid for elid, pos in state['elements']])
                for elid, pos in state['elements']:
                    scene.addElements([levels.real[elid]], QtCore.QPointF(*pos))
                
        self.view = QtWidgets.QGraphicsView(scene)
        self.view.setAcceptDrops(True)
        self.view.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.view.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        #self.view.scene().selectionChanged.connect(self.selectionChanged)
        layout.addWidget(self.view)
        self.view.ensureVisible(0, 0, 1, 1, 0, 0)
                    
    def saveState(self):
        elements = []
        for item in self.view.scene().items():
            elements.append((item.elid, (item.scenePos().x(), item.scenePos().y())))
        return {'elements': elements}
        
mainwindow.addWidgetClass(mainwindow.WidgetClass(
        id = "coverdesk",
        name = translate("CoverDesk", "Coverdesk"),
        icon = utils.getIcon('widgets/coverdesk.png'),
        theClass = CoverDesk,
        areas = 'central, dock',
        preferredDockArea = 'right'))

    
class CoverDeskScene(QtWidgets.QGraphicsScene):
    coverSize = 100
    
    def __init__(self, parent):
        super().__init__(parent)
        
        self.worker = utils.worker.Worker()
        self.worker.start()
        self.coverItems = {}
        self._frontItem = None
        
        self.loadingPixmap = QtGui.QPixmap(':maestro/process-working.png')
        self.loadingTimer = QtCore.QTimer(self)
        self.loadingTimer.setInterval(50) # Timer for loading animation
#         self.reloadCoverTimer = QtCore.QTimer(self)
#         self.reloadCoverTimer.setSingleShot(True)
#         self.reloadCoverTimer.setInterval(1000)
#         self.reloadCoverTimer.timeout.connect(self._handleReloadCoverTimer)

    def addElements(self, elements, position):
        for element in elements:
            if element.hasCover():
                item = CoverItem(self, element.id, element.getCoverPath())
                item.setPos(position)
                self.addItem(item)
        self.loadingTimer.start()

    def selection(self):
        """Return a selection.Selection object based on the selected covers."""
        return selection.Selection.fromElements(levels.real,
                                    levels.real.collect([item.elid for item in self.selectedItems()]))
        
    def helpEvent(self, helpEvent):
        # Note: Setting all tooltips when the scene is generated takes much too long. Reimplementing
        # QGraphicsItem.toolTip does not work for some reason. Thus we reimplement the code that displays
        # tooltips.
        item = self.itemAt(helpEvent.scenePos(), QtGui.QTransform())
        if item is not None:
            QtWidgets.QToolTip.showText(helpEvent.screenPos(), self._createToolTip(item))
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

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(config.options.gui.mime) \
                and Qt.CopyAction & event.possibleActions():
            event.setDropAction(Qt.CopyAction)
            event.acceptProposedAction()
            
    def dragMoveEvent(self, event):
        pass # delete super implementation which only accepts the event, if an item is under the cursor
        
    def dropEvent(self, event):
        mimeData = event.mimeData()
        if not Qt.CopyAction & event.possibleActions():
            return
        event.setDropAction(Qt.CopyAction)
        if mimeData.hasFormat(config.options.gui.mime):
            coverElements = [el for el in mimeData.elements() if el.hasCover()]
            level = mimeData.level
        else:
            logging.warning(__name__, "Invalid drop event (supports only {})"
                                      .format(", ".join(mimeData.formats())))
            return
        
        self.addElements(coverElements, event.scenePos())
        event.acceptProposedAction()
        

class CoverItem(QtWidgets.QGraphicsItem):
    """A GraphicsItem which draws either a cover and a dropshadow or a loading animation."""
    def __init__(self, scene, elid, path):
        super().__init__()
        self.scene = scene
        self.elid = elid
        self.frame = 1 # frame of the loading animation
        self.cover = None
        self._oldCover = None
        self.setCoverPath(path)
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsMovable)
            #QGraphicsItem::ItemIsSelectable |
            #QGraphicsItem::ItemIgnoresTransformations );

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
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable)
    
    def reload(self):
        """Reload the cover from source."""
        self.setCoverPath(self.path)
        
    def _handleTimer(self):
        """React to the scene's loading timer: Move loading animation to the next frame."""
        if self.cover.loaded:
            self.scene.loadingTimer.timeout.disconnect(self._handleTimer)
            self._oldCover = None
        else:
            self.frame += 1
            if self.frame >= 32:
                self.frame = 1
        self.update()
        
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
        if option.state & QtWidgets.QStyle.State_Selected:
            pen.setColor(QtGui.QColor(0,0,255))
        else: pen.setColor(QtGui.QColor(0,0,0))
        painter.setPen(pen)
        painter.drawRect(borderRect)

    def mousePressEvent(self, event):
        if self.scene._frontItem is not None:
            self.scene._frontItem.setZValue(0)
        self.setZValue(1)
        self.scene._frontItem = self
        super().mousePressEvent(event) 
     