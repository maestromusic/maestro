# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2013 Martin Altmayer, Michael Helmling
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

import os.path, collections, functools

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from . import mainwindow, browserdialog, selection, dockwidget
from .misc import busyindicator
from ..models import browser as browsermodel
from .. import database as db, utils, imageloader, config
from ..core import covers, levels, nodes
from ..search import searchbox, criteria

translate = QtCore.QCoreApplication.translate


class CoverBrowser(dockwidget.DockWidget):
    # The option dialog if it is open, and the index of the tab that was active when the dialog was closed.
    _dialog = None
    _lastDialogTabIndex = 0
    
    def __init__(self, parent=None, state=None, **args):
        super().__init__(parent, **args)
        widget = QtGui.QWidget()
        self.setWidget(widget)
        
        layout = QtGui.QVBoxLayout(widget)
        
        controlLineLayout = QtGui.QHBoxLayout()
        self.searchBox = searchbox.SearchBox()
        self.searchBox.criterionChanged.connect(self.search)
        controlLineLayout.addWidget(self.searchBox)
        
        # This option button is only used when dock widget title bars are hidden (otherwise the dock widget
        # title bar contains an analogous button).
        self.optionButton = dockwidget.DockWidgetTitleButton('options')
        self.optionButton.clicked.connect(functools.partial(self.openOptionDialog, self.optionButton))
        controlLineLayout.addWidget(self.optionButton)
        self.optionButton.setVisible(mainwindow.mainWindow.hideTitleBarsAction.isChecked())
        layout.addLayout(controlLineLayout)
        
        self.coverTable = CoverTable()
        self.coverTable.scene().selectionChanged.connect(self._handleSelectionChanged)
        layout.addWidget(self.coverTable,1)
        
        self.flagCriterion = None
        self.filterCriterion = None
        self.searchCriterion = None
        self.searchRequest = None
        
        if browsermodel.searchEngine is None:
            browsermodel.initSearchEngine()
        browsermodel.searchEngine.searchFinished.connect(self._handleSearchFinished)
        self.resultTable = browsermodel.searchEngine.createResultTable("coverbrowser")
        
        if state is not None:
            if 'coverSize' in state and state['coverSize'] is not None:
                self.setCoverSize(state['coverSize'])
                
        self.load()
        
    def saveState(self):
        return {'coverSize': self.getCoverSize()}
        
    def setFlagFilter(self, flags):
        """Set the browser's flag filter to the given list of flags."""
        if len(flags) == 0:
            if self.flagCriterion is not None:
                self.flagCriterion = None
                self.load()
        else:
            if self.flagCriterion is None or self.flagCriterion.flags != flags:
                self.flagCriterion = criteria.FlagCriterion(flags)
                self.load()
        
    def setFilterCriterion(self, criterion):
        """Set a single criterion that will be added to all other criteria from the searchbox (using AND)
        and thus form a permanent filter."""
        if criterion != self.filterCriterion:
            self.filterCriterion = criterion
            self.load()
            
    def search(self):
        self.searchCriterion = self.searchBox.criterion
        self.load()
        
    def load(self):
        """Load contents into the cover browser, based on the current filterCriterion, flagCriterion and
        searchCriterion. If a search is necessary this will only start a search and actual loading will
        be done in _handleSearchFinished.
        """
        if self.searchRequest is not None:
            self.searchRequest.stop()
            self.searchRequest = None
            
        # Combine returns None if all input criteria are None
        criterion = criteria.combine('AND',
                            [c for c in (self.filterCriterion, self.flagCriterion, self.searchBox.criterion)
                             if c is not None])

        if criterion is not None:
            self.table = self.resultTable
            self.searchRequest = browsermodel.searchEngine.search(
                                                  fromTable = db.prefix+"elements",
                                                  resultTable = self.resultTable,
                                                  criterion = criterion)
        else:
            self.table = db.prefix + "elements"
            self.reset()
            
    def _handleSearchFinished(self,request):
        """React to searchFinished signals."""
        if request is self.searchRequest:
            self.searchRequest = None
            #print("FINISHED")
            self.reset()
            
    def reset(self):
        result = db.query("""
            SELECT el.id, st.data
            FROM {1} AS el JOIN {0}stickers AS st ON el.id = st.element_id
            WHERE st.type = 'COVER'
            """.format(db.prefix, self.table))
        
        self.coverTable.scene().setCovers(result)
    
    def getCoverSize(self):
        return self.coverTable.scene().getCoverSize()
    
    def setCoverSize(self, size):
        self.coverTable.scene().setCoverSize(size)
        
    def _handleSelectionChanged(self):
        selection.setGlobalSelection(self.coverTable.scene().selection())
        
    def createOptionDialog(self, parent):
        return BrowserDialog(parent, self)
    
    def _handleHideTitleBarAction(self, checked):
        super()._handleHideTitleBarAction(checked)
        self.optionButton.setVisible(checked)
        

mainwindow.addWidgetData(mainwindow.WidgetData(
        id = "coverbrowser",
        name = translate("CoverBrowser","Cover Browser"),
        icon = utils.getIcon('widgets/coverbrowser.png'),
        theClass = CoverBrowser,
        preferredDockArea = Qt.RightDockWidgetArea))


class CoverTable(QtGui.QGraphicsView):
    """QGraphicsView for the CoverBrowser."""
    def __init__(self):
        super().__init__(CoverTableScene())
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setDragMode(QtGui.QGraphicsView.RubberBandDrag)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.scene()._handleResize() 
        
    
class CoverTableScene(QtGui.QGraphicsScene):
    """QGraphicsScene that contains one CoverItem for each cover and arranges them in a grid."""
    innerSpaceFactor = 3./8. # fraction of coverSize that is used as inner space
    shadowFactor = 1./15. # fraction of coverSize that is used for shadows
    outerSpace = 15 # constant outer space
    
    def __init__(self):
        super().__init__()
        
        self.coverItems = {}
        self._setCoverSize(80)
        covers.addCacheSize(self.coverSize)
        
        self.loadingPixmap = QtGui.QPixmap(':omg/process-working.png')
        self.loadingTimer = QtCore.QTimer(self)
        self.loadingTimer.setInterval(50) # Timer for loading animation
        self.reloadCoverTimer = QtCore.QTimer(self)
        self.reloadCoverTimer.setSingleShot(True)
        self.reloadCoverTimer.setInterval(1000)
        self.reloadCoverTimer.timeout.connect(self._handleReloadCoverTimer)
        
        self.imageLoader = imageloader.ImageLoader()

    def setCovers(self, idsAndPaths):
        """Set the covers that are displayed. *idsAndPaths* must contain tuples of element ids and the
        corresponding cover. The path should point to the original (large) cover, not to a cached version."""
        self.loadingTimer.stop()
        self.clear()
        self.coverItems = collections.OrderedDict((id, CoverItem(self, id, path)) for id,path in idsAndPaths)
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
        return self.coverSize
    
    def setCoverSize(self, size):
        assert size is not None
        if size != self.coverSize:
            self._setCoverSize(size)
            self.arrange()
            self.reloadCoverTimer.start()
        for item in self.coverItems.values():
            item.update()
            
    def _setCoverSize(self, size):
        self.coverSize = size
        self.innerSpace = int(self.innerSpaceFactor * size)
        newShadowOffset = int(round(self.shadowFactor * size))
        if not hasattr(self,'shadowOffset') or newShadowOffset != self.shadowOffset:
            self.shadowOffset = newShadowOffset
            for item in self.coverItems.values():
                if item.graphicsEffect() is not None:
                    item.graphicsEffect().setOffset(newShadowOffset)
            
    def selection(self):
        """Return a Selection object based on the selected covers."""
        return selection.Selection.fromElements(levels.real,
                                    levels.real.collectMany([item.elid for item in self.selectedItems()]))
            

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
        self.cover = covers.getAsync(self.scene.imageLoader, path, self.scene.coverSize)
        if not self.cover.loaded:
            self.scene.loadingTimer.timeout.connect(self._handleTimer)
        else: self._addShadow()
        self.setFlag(QtGui.QGraphicsItem.ItemIsSelectable)
    
    def reload(self):
        """Reload the cover from source."""
        self.setCoverPath(self.path)
        
    def _handleTimer(self):
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
        if self.cover.loaded:
            painter.drawPixmap(1, 1, self.scene.coverSize, self.scene.coverSize, self.cover.pixmap)
        elif self._oldCover is not None:
            painter.drawPixmap(1, 1, self.scene.coverSize, self.scene.coverSize, self._oldCover.pixmap)
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
        pen = painter.pen()
        if option.state & QtGui.QStyle.State_Selected:
            pen.setColor(QtGui.QColor(0,0,255))
        else: pen.setColor(QtGui.QColor(0,0,0))
        painter.setPen(pen)
        painter.drawRect(0, 0, self.scene.coverSize+1, self.scene.coverSize+1)
        
    def mouseMoveEvent(self, event):
        if QtCore.QLineF(QtCore.QLine(event.screenPos(), event.buttonDownScreenPos(Qt.LeftButton))).length() \
                > QtGui.QApplication.startDragDistance():
            drag = QtGui.QDrag(event.widget())
            mimeData = selection.MimeData(self.scene.selection())
            drag.setMimeData(mimeData)
            drag.exec_()
            self.setCursor(Qt.OpenHandCursor)
            
            
class BrowserDialog(browserdialog.AbstractBrowserDialog):
    def __init__(self, parent, browser):
        super().__init__(parent, browser)
        optionLayout = self.optionTab.layout()
                
        instantSearchBox = QtGui.QCheckBox(self.tr("Instant search"))
        instantSearchBox.setChecked(self.browser.searchBox.getInstantSearch())
        instantSearchBox.clicked.connect(self.browser.searchBox.setInstantSearch)
        optionLayout.addWidget(instantSearchBox)
        
        lineLayout = QtGui.QHBoxLayout()
        lineLayout.addWidget(QtGui.QLabel(self.tr("Cover size: ")))
        self.sizeSlider = QtGui.QSlider(Qt.Horizontal) 
        self.sizeSlider.setMinimum(20)
        self.sizeSlider.setMaximum(100)
        self.sizeSlider.setValue(browser.coverTable.scene().getCoverSize())
        lineLayout.addWidget(self.sizeSlider)
        sizeLabel = QtGui.QLabel(str(browser.coverTable.scene().getCoverSize()))
        self.sizeSlider.valueChanged.connect(lambda x: sizeLabel.setText(str(x)))
        lineLayout.addWidget(sizeLabel)
        self.sizeSlider.valueChanged.connect(browser.setCoverSize)
        optionLayout.addLayout(lineLayout)
        
        optionLayout.addStretch(1)
        