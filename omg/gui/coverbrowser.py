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

import os.path

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from . import mainwindow, browserdialog, selection
from .misc import busyindicator
from ..models import browser as browsermodel
from .. import database as db, utils, imageloader, config
from ..core import covers, levels, nodes
from ..search import searchbox

translate = QtCore.QCoreApplication.translate


class CoverBrowserDock(QtGui.QDockWidget):
    """DockWidget containing the TagEditor."""
    def __init__(self,parent=None,state=None,location=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Cover Browser"))
        
        self.browser = CoverBrowser()
        self.setWidget(self.browser)


mainwindow.addWidgetData(mainwindow.WidgetData(
        id="coverbrowser",
        name=translate("CoverBrowser","Cover Browser"),
        theClass = CoverBrowserDock,
        central=True,
        dock=True,
        default=False,
        unique=False,
        preferredDockArea=Qt.RightDockWidgetArea))


class CoverBrowser(QtGui.QWidget):   
    
    # The option dialog if it is open, and the index of the tab that was active when the dialog was closed.
    _dialog = None
    _lastDialogTabIndex = 0
    
    def __init__(self):
        super().__init__()
        layout = QtGui.QVBoxLayout(self)
        
        # ControlLine (containing searchBox and optionButton)
        controlLineLayout = QtGui.QHBoxLayout()
        layout.addLayout(controlLineLayout)
        
        self.searchBox = searchbox.SearchBox(self)
        self.searchBox.criteriaChanged.connect(self.search)
        controlLineLayout.addWidget(self.searchBox)
        
        self.optionButton = QtGui.QPushButton(self)
        self.optionButton.setIcon(utils.getIcon('options.png'))
        self.optionButton.clicked.connect(self._handleOptionButton)
        controlLineLayout.addWidget(self.optionButton)
        
        self.coverTable = CoverTable()
        self.coverTable.scene().selectionChanged.connect(self._handleSelectionChanged)
        layout.addWidget(self.coverTable,1)
        
        self.criterionFilter = []
        self.searchCriteria = []
        self.searchRequest = None
        
        if browsermodel.searchEngine is None:
            browsermodel.initSearchEngine()
        browsermodel.searchEngine.searchFinished.connect(self._handleSearchFinished)
        self.bigResult = browsermodel.searchEngine.createResultTable("browser_big")
        
        self._imageLoader = imageloader.ImageLoader()
        #self._imageLoader.loaded.connect(self.coverTable.inner.update)
        self.load()
    
    def _handleOptionButton(self):
        """Open the option dialog."""
        self._dialog = BrowserDialog(self)
        self._dialog.tabWidget.setCurrentIndex(self._lastDialogTabIndex)
        self._dialog.show()
    
    def _handleDialogClosed(self):
        """Close the option dialog."""
        # Note: This is called by the dialog and not by a signal
        if self._dialog is not None:
            self._lastDialogTabIndex = self._dialog.tabWidget.currentIndex()
            self._dialog = None
        
    def setCriterionFilter(self,criteria):
        """Set the criterion filter. This is a list of criteria that will be prepended to the search criteria
        from the searchbox and thus form a permanent filter."""
        if criteria != self.criterionFilter:
            self.criterionFilter = criteria[:]
            self.load()
            
    def search(self):
        self.searchCriteria = self.searchBox.getCriteria()
        self.load()
        
    def load(self):
        criteria = self.criterionFilter + self.searchCriteria
        # This will effectively stop any request from being processed
        if self.searchRequest is not None:
            self.searchRequest.stop()
            self.searchRequest = None

        if len(criteria) > 0:
            self.table = self.bigResult
            self.searchRequest = browsermodel.searchEngine.search(fromTable = db.prefix+"elements",
                                                                  resultTable = self.bigResult,
                                                                  criteria = criteria
                                                                )
            # self.reset will be called when the search is finished
        else:
            self.table = db.prefix + "elements"
            self.searchRequest = None
            self.reset()
            
    def _handleSearchFinished(self,request):
        """React to searchFinished signals: Set the table to self.bigResult and reset the model."""
        if request is self.searchRequest:
            self.searchRequest = None
            #print("FINISHED")
            self.reset()
            
    def reset(self):
        result = db.query("""
            SELECT el.id,dat.data
            FROM {1} AS el JOIN {0}data AS dat ON el.id = dat.element_id
            WHERE dat.type = 'COVER'
            """.format(db.prefix,self.table))
        
        self.coverTable.setCovers([(id,covers.getAsync(self._imageLoader, path, self.coverTable.getCoverSize()))
                                   for id,path in result])
            
    def setCoverSize(self,size):
        self.coverTable.setCoverSize(size)
        
    def _handleSelectionChanged(self):
        selection.setGlobalSelection(self.coverTable.scene().selection())
    

class CoverItem(QtGui.QGraphicsItem):
    def __init__(self, scene, elid, cover):
        super().__init__()
        self.scene = scene
        self.cover = cover
        self.elid = elid
        self.frame = 1
        if not cover.loaded:
            self.scene.loadingTimer.timeout.connect(self._handleTimer)
        else: self._addShadow()
        self.setFlag(QtGui.QGraphicsItem.ItemIsSelectable)
    
    def _handleTimer(self):
        if self.cover.loaded:
            self.scene.loadingTimer.timeout.disconnect(self._handleTimer)
            self._addShadow()
        else:
            self.frame += 1
            if self.frame >= 32:
                self.frame = 1
        self.update()
        
    def _addShadow(self):
        effect = QtGui.QGraphicsDropShadowEffect()
        effect.setOffset(5)
        self.setGraphicsEffect(effect)
        
    def boundingRect(self):
        return QtCore.QRectF(0, 0, self.scene.coverSize+2, self.scene.coverSize+2)
    
    def paint(self, painter, option, widget):
        if self.cover.loaded:
            painter.drawPixmap(1, 1, self.scene.coverSize, self.scene.coverSize, self.cover.pixmap)
        else:
            destXY = (self.scene.coverSize-32) // 2 + 1 # +1: adjust for border
            srcX = 32 * (self.frame % 8)
            srcY = 32 * (self.frame // 8)
            painter.drawPixmap(destXY, destXY, self.scene.loadingPixmap, srcX, srcY, 32, 32)
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
        
        
class CoverTable(QtGui.QGraphicsView):
    def __init__(self):
        super().__init__(CoverTableScene())
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setDragMode(QtGui.QGraphicsView.RubberBandDrag)
        
    def setCovers(self, covers):
        self.scene().setCovers(covers)
    
    def getCoverSize(self):
        return self.scene().getCoverSize()
    
    def setCoverSize(self, size):
        self.scene().setCoverSize(size)
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.scene().resized() 
        
    
class CoverTableScene(QtGui.QGraphicsScene):
    def __init__(self):
        super().__init__()
        
        #self.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(50,50,50)))
        self.paths = []
        self.coverSize = 80
        self.availableWidth = 600
        self.innerSpace = 30
        self.outerSpace = 15
        
        self.loadingPixmap = QtGui.QPixmap(':omg/process-working.png')
        self.loadingTimer = QtCore.QTimer(self)
        self.loadingTimer.setInterval(50)

    def setCovers(self, covers):
        self.covers = covers
        self._fillScene()
        
    def resized(self):
        if self.columnCount != self._computeColumnCount():
            self._fillScene()
            
    def _computeColumnCount(self):
        availableWidth = self.views()[0].viewport().width() - 2*self.outerSpace
        return max(1, (availableWidth+self.innerSpace) // (self.coverSize+self.innerSpace))
        
    def _fillScene(self):
        self.loadingTimer.stop()
        self.clear()
        self.columnCount = self._computeColumnCount()
        
        row = column = 0
        for elid, cover in self.covers:
            item = CoverItem(self, elid, cover)
            item.setPos(self._getPos(row, column))
            self.addItem(item)
            column += 1
            if column == self.columnCount:
                column = 0
                row += 1
        totalRows = row+1 if column != 0 else row
        totalColumns = min(self.columnCount, len(self.covers))
        self.setSceneRect(0, 0,
                      2*self.outerSpace + totalColumns * (self.coverSize+self.innerSpace) - self.innerSpace,
                      2*self.outerSpace + totalRows * (self.coverSize+self.innerSpace) - self.innerSpace)
        self.loadingTimer.start()
                
    def _getPos(self, row, column):
        x = self.outerSpace + column * (self.coverSize + self.innerSpace)
        y = self.outerSpace + row * (self.coverSize + self.innerSpace)
        return QtCore.QPointF(x,y)
    
    def getCoverSize(self):
        return self.coverSize
    
    def setCoverSize(self, size):
        if size != self.coverSize:
            self.coverSize = size
            self._fillScene()
            
    def selection(self):
        return selection.Selection.fromElements(levels.real,
                                    levels.real.collectMany([item.elid for item in self.selectedItems()]))
            
            
class BrowserDialog(browserdialog.AbstractBrowserDialog):
    def __init__(self, browser):
        super().__init__(browser)
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
        self.sizeSlider.setValue(browser.coverTable.getCoverSize())
        lineLayout.addWidget(self.sizeSlider)
        sizeLabel = QtGui.QLabel(str(browser.coverTable.getCoverSize()))
        self.sizeSlider.valueChanged.connect(lambda x: sizeLabel.setText(str(x)))
        lineLayout.addWidget(sizeLabel)
        self.sizeSlider.valueChanged.connect(browser.setCoverSize)
        optionLayout.addLayout(lineLayout)
        
        optionLayout.addStretch(1)
        