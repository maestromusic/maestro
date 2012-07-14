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

from ...core import commands
from ...core.elements import Element
from ...gui import treeactions


coverProviderClasses = []

BIG_COVER_SIZE = 400

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
    
coverProviderClasses.append(DummyProviderClass)

    
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
            

class CoverDialog(QtGui.QDialog):
    def __init__(self,parent,level,elids):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Edit covers"))
        self.stack = QtGui.QUndoStack()
        self.level = level.subLevel(elids,"coverdialog")
        self.level.changed.connect(self._handleLevelChanged)
        
        self.elements = [self.level.get(id) for id in elids]
        self.availableCovers = {}
        self.coverProviders = []
        self.coverProviderButtons = {}
        
        for element in self.elements:
            self.availableCovers[element] = []
            if element.hasCover():
                self.availableCovers[element].append(Cover(element.getCoverPath()))
        
        style = QtGui.QApplication.style()
        
        self.setLayout(QtGui.QVBoxLayout())
        layout = QtGui.QHBoxLayout()
        self.layout().addLayout(layout)
        
        
        self.elementList = QtGui.QListWidget()
        self.elementList.setIconSize(QtCore.QSize(40,40))
        self.elementList.currentItemChanged.connect(self._handleCurrentElementChanged)
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
        
        for coverProviderClass in coverProviderClasses:
            coverProvider = coverProviderClass()
            coverProvider.finished.connect(functools.partial(self._handleCoverProviderFinished,coverProvider))
            self.coverProviders.append(coverProvider)
            
            button = QtGui.QPushButton(self.tr("Fetch from {}").format(coverProviderClass.name()))
            if coverProviderClass.icon() is not None:
                button.setIcon(coverProviderClass.icon())
            button.clicked.connect(functools.partial(self._handleCoverProviderButton,coverProvider))
            coverButtonLayout.addWidget(button)
            self.coverProviderButtons[coverProvider] = button
            
        coverButtonLayout.addStretch()
        
        self.removeCoverButton = QtGui.QPushButton(self.tr("Remove cover"))
        self.removeCoverButton.clicked.connect(self._handleRemoveButton)
        coverButtonLayout.addWidget(self.removeCoverButton)
            
        self.coverList = QtGui.QListWidget()
        self.coverList.setFlow(QtGui.QListView.LeftToRight)
        self.coverList.setIconSize(QtCore.QSize(100,100))
        self.coverList.currentItemChanged.connect(self._handleCurrentCoverChanged)
        rightLayout.addWidget(self.coverList)
        
        rightLayout.addStretch()
        
        # Buttons
        buttonLayout = QtGui.QHBoxLayout()
        self.layout().addLayout(buttonLayout)
        
        undoButton = QtGui.QPushButton(self.tr("Undo"))
        undoButton.clicked.connect(self.stack.undo)
        self.stack.canUndoChanged.connect(undoButton.setEnabled)
        undoButton.setEnabled(False)
        buttonLayout.addWidget(undoButton)
        redoButton = QtGui.QPushButton(self.tr("Redo"))
        redoButton.clicked.connect(self.stack.redo)
        self.stack.canRedoChanged.connect(redoButton.setEnabled)
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
        
        self.currentElement = None
        self._fillElementsList()
        self.elementList.setCurrentItem(self.elementList.item(0)) # will call setElement
        self._startFetchingCovers()
        
    def _fillElementsList(self):
        self.elementList.clear()
        for element in self.elements:
            item = QtGui.QListWidgetItem(element.getTitle())
            item.setData(Qt.UserRole,element)
            if element.hasCover():
                cover = element.getCover()
                item.setIcon(QtGui.QIcon(cover))
            self.elementList.addItem(item)
            
    def setElement(self,element):
        if element != self.currentElement:
            self.currentElement = element
            self._updateLabel()
            self._fillAvailableCovers()
            
            for coverProvider,button in self.coverProviderButtons.items():
                button.setEnabled(not coverProvider.hasFinished(element))
                
            self.removeCoverButton.setEnabled(self.currentElement.hasCover())
    
    def _fillAvailableCovers(self):
        self.coverList.clear()
        for cover in self.availableCovers[self.currentElement]:
            pixmap = cover.pixmap
            item = QtGui.QListWidgetItem("{}x{}".format(pixmap.width(),pixmap.height()))
            item.setIcon(QtGui.QIcon(pixmap))
            item.setData(Qt.UserRole,cover)
            if cover.path is not None:
                item.setData(Qt.ToolTipRole,cover.path)
            self.coverList.addItem(item)
            if cover.path is not None and cover.path == self.currentElement.getCoverPath():
                #self.coverList.setCurrentItem(item)
                pass #TODO
    
    def _updateLabel(self):
        element = self.currentElement
        if element.hasCover():
            pixmap = element.getCover()
            if pixmap.width() > BIG_COVER_SIZE or pixmap.height() > BIG_COVER_SIZE:
                pixmap = pixmap.scaled(400,400,transformMode=Qt.SmoothTransform)
            self.label.setPixmap(pixmap)
        else: self.label.setPixmap(QtGui.QPixmap())
        
    def addAvailableCovers(self,coverDict):
        for element,covers in coverDict.items():
            self.availableCovers[element].extend(covers)
            if element == self.currentElement:
                self._fillAvailableCovers()
                
    def _handleCoverProviderFinished(self,provider,coverDict):
        if self.currentElement in coverDict:
            self.coverProviderButtons[provider].setEnabled(False)
        self.addAvailableCovers(coverDict)
            
    def _handleCurrentElementChanged(self,current,previous):
        self.setElement(current.data(Qt.UserRole))
        
    def _handleCurrentCoverChanged(self,current,previous):
        if current is None:
            return
        cover = current.data(Qt.UserRole)
        print("_handleCurrentCoverChanged: {}".format(cover.path))
        if cover.path is None: # only a pixmap is contained
            self.level.setCover(self.stack,self.currentElement,cover.pixmap)
            cover.path = self.currentElement.getCoverPath()
            current.setData(Qt.ToolTipRole,cover.path)
        elif cover.path != self.currentElement.getCoverPath():
            self.level.setCover(self.stack,self.currentElement,cover.path)
            
    def _startFetchingCovers(self):
        elementsWithoutCover = [element for element in self.elements if not element.hasCover()]
        if len(elementsWithoutCover) > 0:
            for coverProvider in self.coverProviders:
                coverProvider.fetch(elementsWithoutCover)
            
    def _handleLevelChanged(self,event):
        for id in event.dataIds:
            element = self.level.get(id)
            for i in range(self.elementList.count()):
                item = self.elementList.item(i)
                if item.data(Qt.UserRole) == element:
                    if element.hasCover():
                        item.setIcon(QtGui.QIcon(element.getCover()))
                    else: item.setIcon(QtGui.QIcon())
                    break
                
        if self.currentElement.id in event.dataIds:
            self._updateLabel()
            if self.currentElement.getCoverPath() is None:
                print("Remove current item")
                self.coverList.setCurrentRow(-1)
            else:
                for i in range(self.coverList.count()):
                    item = self.coverList.item(i)
                    if item.data(Qt.UserRole).path == self.currentElement.getCoverPath():
                        print("Set current item {}".format(i))
                        #TODOself.coverList.setCurrentItem(item)
                        break
            self.removeCoverButton.setEnabled(self.currentElement.hasCover())
        
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
            self.level.setCover(self.stack,self.currentElement,pixmap)
            cover = Cover(path=self.currentElement.getCoverPath())
            self.addAvailableCovers({self.currentElement: [cover]})
        
    def _handleCoverProviderButton(self,coverProvider):
        coverProvider.fetch([self.currentElement])
        
    def _handleRemoveButton(self):
        self.level.setCover(self.stack,self.currentElement,None)
        
        