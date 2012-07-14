# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
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

import os.path, functools

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ...core import commands, covers
from ...core.elements import Element
from ...gui import treeactions


BIG_COVER_SIZE = 400
AVAILABLE_COVER_SIZE = 100
SMALL_COVER_SIZE = 40


def enable():
    from omg.gui import editor, browser
    editor.EditorTreeView.actionConfig.addActionDefinition((("plugins", 'renamer'),), CoverAction)
    browser.BrowserTreeView.actionConfig.addActionDefinition((("plugins", 'renamer'),), CoverAction)
        
def disable():
    editor.EditorTreeView.actionConfig.removeActionDefinition((("plugins", 'covers'),))
    browser.BrowserTreeView.actionConfig.removeActionDefinition((("plugins", 'covers'),))


class DummyProviderClass(QtCore.QObject):
    finished = QtCore.pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        self._finished = []
        
    @staticmethod
    def icon():
        return QtGui.QIcon(":omg/lastfm.gif")
    @staticmethod
    def name():
        return "Last.fm"
    
    def fetch(self,elements):
        assert not any(element in self._finished for element in elements)
        self.elements = elements
        QtCore.QTimer.singleShot(200,self._handleTimer)
        
    def _handleTimer(self):
        self._finished.extend(self.elements)
        self.finished.emit({element: [Cover(pixmap=QtGui.QPixmap("/home/martin/Musik/stravinsky.jpg"))]
                            for element in self.elements})
    
    def hasFinished(self,element):
        return element in self._finished
    
covers.providerClasses.append(DummyProviderClass)

    
class CoverAction(treeactions.TreeAction):
    """Action to rename files in a container according to the tags and the container structure."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.setText(self.tr('Edit covers...'))
    
    def initialize(self):
        self.setEnabled(self.parent().nodeSelection.hasWrappers())
    
    def doAction(self):
        dialog = CoverDialog(self.parent(), self.level(),
                              [wrap.element.id for wrap in self.parent().nodeSelection.wrappers()])
        dialog.exec_()
        if dialog.result() == dialog.Accepted:
            application.stack.push(commands.CommitCommand(dialog.level,dialog.ids,self.tr("Edit covers")))
            
            
class Cover:
    def __init__(self,path=None,pixmap=None):
        assert path is not None or pixmap is not None
        self.path = path
        if pixmap is not None:
            self.pixmap = pixmap
        else: self.pixmap = QtGui.QPixmap(path)
            

class CoverDialogModel(QtCore.QObject):
    providerStatusChanged = QtCore.pyqtSignal()
    availableCoversChanged = QtCore.pyqtSignal()
    currentCoverChanged = QtCore.pyqtSignal()
    
    def __init__(self,stack,level,elids):
        super().__init__()
        self.stack = stack
        self.level = level
        self.level.changed.connect(self._handleLevelChanged)
        self.elements = level.getFromIds(elids)
        self.currentElement = self.elements[0]
                                 
        # Initialize available covers        
        self.availableCovers = {}
        for element in self.elements:
            self.availableCovers[element] = []
            if element.hasCover():
                self.availableCovers[element].append(Cover(element.getCoverPath()))
                
        # Initialize cover providers
        self.coverProviders = []
        for providerClass in covers.providerClasses:
            coverProvider = providerClass()
            coverProvider.finished.connect(self._handleProviderFinished)
            self.coverProviders.append(coverProvider)
    
    def startFetchingCovers(self):
        elementsWithoutCover = [element for element in self.elements if not element.hasCover()]
        if len(elementsWithoutCover) > 0:
            for coverProvider in self.coverProviders:
                coverProvider.fetch(elementsWithoutCover)
            
    def _handleProviderFinished(self,coverDict):
        if self.currentElement in coverDict:
            self.providerStatusChanged.emit()
        self.addAvailableCovers(coverDict)
                
    def addAvailableCovers(self,coverDict):
        for element,covers in coverDict.items():
            self.availableCovers[element].extend(covers)
        if self.currentElement in coverDict:
            self.availableCoversChanged.emit()
         
    def setElement(self,element):
        if element != self.currentElement:
            self.currentElement = element
            self.currentCoverChanged.emit()
            self.availableCoversChanged.emit()
            self.providerStatusChanged.emit()
    
    def setCover(self,cover):
        if cover.path is not None:
            if cover.path != self.currentElement.getCoverPath():
                self.level.setCover(self.stack,self.currentElement,cover.path)
        else:
            self.level.setCover(self.stack,self.currentElement,cover.pixmap)
            cover.path = self.currentElement.getCoverPath()
        
    def removeCover(self):
        self.level.setCover(self.stack,self.currentElement,None)
            
    def _handleLevelChanged(self,event):               
        if self.currentElement.id in event.dataIds:
            self.currentCoverChanged.emit()
            self.availableCoversChanged.emit()
        
        
class CoverDialog(QtGui.QDialog):
    def __init__(self,parent,level,elids):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Edit covers"))
        
        level = level.subLevel(elids,"coverdialog")
        self.model = CoverDialogModel(QtGui.QUndoStack(),level,elids)
        self.model.providerStatusChanged.connect(self._handleProviderStatusChanged)
        self.model.availableCoversChanged.connect(self._fillAvailableCovers)
        self.model.currentCoverChanged.connect(self._handleCurrentCoverChanged)
        level.changed.connect(self._handleLevelChanged)
                
        style = QtGui.QApplication.style()
        
        self.setLayout(QtGui.QVBoxLayout())
        layout = QtGui.QHBoxLayout()
        self.layout().addLayout(layout)
        
        self.elementList = QtGui.QListWidget()
        self.elementList.setIconSize(QtCore.QSize(SMALL_COVER_SIZE,SMALL_COVER_SIZE))
        self.elementList.currentItemChanged.connect(self._handleElementSelected)
        layout.addWidget(self.elementList)
        
        rightLayout = QtGui.QVBoxLayout()
        layout.addLayout(rightLayout)
        
        rightTopLayout = QtGui.QHBoxLayout()
        rightLayout.addLayout(rightTopLayout)
        self.label = QtGui.QLabel()
        self.label.setMinimumSize(BIG_COVER_SIZE,BIG_COVER_SIZE)
        self.label.setAlignment(Qt.AlignCenter)
        rightTopLayout.addWidget(self.label,1)
        
        coverButtonLayout = QtGui.QVBoxLayout()
        rightTopLayout.addLayout(coverButtonLayout)
        
        openFromFileButton = QtGui.QPushButton(style.standardIcon(QtGui.QStyle.SP_DialogOpenButton),
                                               self.tr("Open from file..."))
        openFromFileButton.clicked.connect(self._handleOpenFromFile)
        coverButtonLayout.addWidget(openFromFileButton)
        
        openFromURLButton = QtGui.QPushButton(self.tr("Open from URL..."))
        coverButtonLayout.addWidget(openFromURLButton)
        
        self.providerButtons = {}
        for coverProvider in self.model.coverProviders:
            button = QtGui.QPushButton(self.tr("Fetch from {}").format(coverProvider.name()))
            if coverProvider.icon() is not None:
                button.setIcon(coverProvider.icon())
            button.clicked.connect(functools.partial(self._handleProviderButton,coverProvider))
            self.providerButtons[coverProvider] = button
            coverButtonLayout.addWidget(button)
            
        coverButtonLayout.addStretch()
        
        self.removeCoverButton = QtGui.QPushButton(self.tr("Remove cover"))
        self.removeCoverButton.clicked.connect(self.model.removeCover)
        coverButtonLayout.addWidget(self.removeCoverButton)
            
        self.coverList = QtGui.QListWidget()
        self.coverList.setFlow(QtGui.QListView.LeftToRight)
        self.coverList.setIconSize(QtCore.QSize(AVAILABLE_COVER_SIZE,AVAILABLE_COVER_SIZE))
        self.coverList.itemSelectionChanged.connect(self._handleCoverSelected)
        rightLayout.addWidget(self.coverList)
        
        rightLayout.addStretch()
        
        # Buttons
        buttonLayout = QtGui.QHBoxLayout()
        self.layout().addLayout(buttonLayout)
        
        undoButton = QtGui.QPushButton(self.tr("Undo"))
        undoButton.clicked.connect(self.model.stack.undo)
        self.model.stack.canUndoChanged.connect(undoButton.setEnabled)
        undoButton.setEnabled(False)
        buttonLayout.addWidget(undoButton)
        redoButton = QtGui.QPushButton(self.tr("Redo"))
        redoButton.clicked.connect(self.model.stack.redo)
        self.model.stack.canRedoChanged.connect(redoButton.setEnabled)
        redoButton.setEnabled(False)
        buttonLayout.addWidget(redoButton)
        
        buttonLayout.addStretch()
        
        resetButton = QtGui.QPushButton(style.standardIcon(QtGui.QStyle.SP_DialogResetButton),
                                             self.tr("Reset"))
        #resetButton.clicked.connect(self._handleReset)
        cancelButton = QtGui.QPushButton(style.standardIcon(QtGui.QStyle.SP_DialogCancelButton),
                                             self.tr("Cancel"))
        cancelButton.clicked.connect(self.reject)
        commitButton = QtGui.QPushButton(style.standardIcon(QtGui.QStyle.SP_DialogSaveButton),
                                         self.tr("OK"))
        #commitButton.clicked.connect(self._handleCommit)
        
        buttonLayout.addWidget(resetButton)
        buttonLayout.addWidget(cancelButton)
        buttonLayout.addWidget(commitButton)
        
        
        # Fill element list
        for element in self.model.elements:
            item = QtGui.QListWidgetItem(element.getTitle())
            item.setData(Qt.UserRole,element)
            if element.hasCover():
                cover = element.getCover()
                item.setIcon(QtGui.QIcon(cover))
            self.elementList.addItem(item)
        self.elementList.setCurrentItem(self.elementList.item(0)) # will call setElement
        
        self.model.startFetchingCovers()
        self._fillAvailableCovers()
        self._handleCurrentCoverChanged()
        
    def _handleProviderStatusChanged(self):
        for provider,button in self.providerButtons.items():
            button.setEnabled(not provider.hasFinished(self.model.currentElement))
    
    def _fillAvailableCovers(self):
        print("_fillAvailableCovers")
        self.coverList.clear()
        for cover in self.model.availableCovers[self.model.currentElement]:
            pixmap = cover.pixmap
            item = QtGui.QListWidgetItem("{}x{}".format(pixmap.width(),pixmap.height()))
            item.setIcon(QtGui.QIcon(pixmap))
            item.setData(Qt.UserRole,cover)
            if cover.path is not None:
                item.setData(Qt.ToolTipRole,cover.path)
            self.coverList.addItem(item)
            if cover.path is not None and cover.path == self.model.currentElement.getCoverPath():
                item.setSelected(True)
                self.coverList.setCurrentItem(item)
    
    def _handleCurrentCoverChanged(self):
        #print("_handleCurrentCoverChanged")
        element = self.model.currentElement
        if element.hasCover():
            pixmap = element.getCover()
            if pixmap.width() > BIG_COVER_SIZE or pixmap.height() > BIG_COVER_SIZE:
                pixmap = pixmap.scaled(BIG_COVER_SIZE,BIG_COVER_SIZE,transformMode=Qt.SmoothTransform)
            self.label.setPixmap(pixmap)
        else: self.label.setPixmap(QtGui.QPixmap())
        
        for i in range(self.coverList.count()):
            item = self.coverList.item(i)
            cover = item.data(Qt.UserRole)
            if element.hasCover() and element.getCoverPath() == cover.path:
                item.setSelected(True)
                self.coverList.setCurrentItem(item)
            else: item.setSelected(False)
            
        self.removeCoverButton.setEnabled(element.hasCover())
    
    def _handleElementSelected(self,current,previous):
        self.model.setElement(current.data(Qt.UserRole))
                
    def _handleCoverSelected(self):
        selectedItems = self.coverList.selectedItems()
        print("_handleCoverSelected {}".format([item.data(Qt.UserRole).path for item in selectedItems]))
        if len(selectedItems) == 0:
            return # This happens due to self.coverList.clear in _fillAvailableCovers
        cover = selectedItems[0].data(Qt.UserRole)
        self.model.setCover(cover)
            
    def _handleOpenFromFile(self):
        fileName = QtGui.QFileDialog.getOpenFileName(
                                                self,
                                                self.tr("Open cover file"),
                                                os.path.expanduser("~"),
                                                self.tr("Image files (*.png *.jpg *.bmp);;All files (*)"))
        if fileName == "": # user canceled the dialog
            return
        
        pixmap = QtGui.QPixmap(fileName)
        if pixmap.isNull():
            QtGui.QMessageBox(QtGui.QMessageBox.Warning,self.tr("Failed to open the file"),
                              self.tr("The file could not be opened."),QtGui.QMessageBox.Ok,self).exec_()
        else:
            cover = Cover(pixmap=pixmap)
            self.model.setCover(cover)
            self.model.addAvailableCovers({self.model.currentElement: [cover]})
        
    def _handleProviderButton(self,coverProvider):
        coverProvider.fetch([self.model.currentElement])
        
    def _handleLevelChanged(self,event):
        for i in range(self.elementList.count()):
            item = self.elementList.item(i)
            element = item.data(Qt.UserRole)
            if element.id in event.dataIds:
                if element.hasCover():
                    item.setIcon(QtGui.QIcon(element.getCover()))
                else: item.setIcon(QtGui.QIcon())
                