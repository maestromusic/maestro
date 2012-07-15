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

from PyQt4 import QtCore, QtGui, QtNetwork
from PyQt4.QtCore import Qt

from ...core import commands, covers
from ...core.elements import Element
from ...gui import treeactions
from ... import application


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


class DummyProvider(covers.AbstractCoverProvider):       
    @staticmethod
    def icon():
        return QtGui.QIcon("/home/martin/temp/beta.png")
    @staticmethod
    def name():
        return "Dummy"
    
    def fetch(self,elements):
        self.elements = elements
        QtCore.QTimer.singleShot(200,self._handleTimer)
        
    def _handleTimer(self):
        for element in self.elements:
            self.loaded.emit(element,QtGui.QPixmap("/home/martin/Musik/stravinsky.jpg"))
            self.finished.emit(element)
    
#covers.providerClasses.append(DummyProviderClass)

    
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
    def __init__(self,path=None,pixmap=None,text=None):
        assert path is not None or pixmap is not None
        self.path = path
        if pixmap is not None:
            self.pixmap = pixmap
        else: self.pixmap = QtGui.QPixmap(path)
        self.text = text
        
    def __eq__(self,other):
        if self.path is not None:
            return self.path == other.path
        else: return self is other
        
    def __ne__(self,other):
        if self.path is not None:
            return self.path != other.path
        else: return self is not other
        
            

class CoverUndoCommand(QtGui.QUndoCommand):
    def __init__(self,model,element,new):
        super().__init__()
        self.model = model
        self.element = element
        self.old = model.getCover(element)
        self.new = new
        
    def redo(self):
        self.model._setCover(self.element,self.new)
        
    def undo(self):
        self.model._setCover(self.element,self.old)
        
        
class CoverDialogModel(QtCore.QObject):
    providerStatusChanged = QtCore.pyqtSignal()
    availableCoversChanged = QtCore.pyqtSignal()
    currentCoverChanged = QtCore.pyqtSignal()
    coverChanged = QtCore.pyqtSignal(Element)
    error = QtCore.pyqtSignal(str)
    
    def __init__(self,stack,level,elids):
        super().__init__()
        self.stack = stack
        self.level = level
        self.elements = level.getFromIds(elids)
        self.currentElement = self.elements[0]
                                 
        # Initialize available covers
        self.availableCovers = {}
        self.currentCovers = {}
        self._fetchedCovers = {}
        for element in self.elements:
            self.availableCovers[element] = []
            if element.hasCover():
                cover = Cover(element.getCoverPath())
                self.availableCovers[element].append(cover)
                self.currentCovers[element] = cover
            else: self.currentCovers[element] = None
                
        # Initialize cover providers
        self.coverProviders = []
        for providerClass in covers.providerClasses:
            coverProvider = providerClass()
            coverProvider.loaded.connect(functools.partial(self._handleProviderLoaded,coverProvider))
            coverProvider.error.connect(functools.partial(self._handleProviderError,coverProvider))
            coverProvider.finished.connect(functools.partial(self._handleProviderFinished,coverProvider))
            self.coverProviders.append(coverProvider)
    
    def startFetchingCovers(self):
        elementsWithoutCover = [element for element in self.elements if not element.hasCover()]
        if len(elementsWithoutCover) > 0:
            for element in elementsWithoutCover:
                self._fetchedCovers[element] = []
            for coverProvider in self.coverProviders:
                coverProvider.fetch(elementsWithoutCover)
            
    def _handleProviderLoaded(self,provider,element,pixmap):
        if element is self.currentElement:
            self.providerStatusChanged.emit()
        cover = Cover(pixmap=pixmap,text=provider.name())
        self._fetchedCovers[element].append(cover)
        self.addAvailableCovers({element: [cover]})
    
    def _handleProviderError(self,provider,message):
        self.error.emit(self.tr("{}: {}").format(provider.name(),message))
        
    def _handleProviderFinished(self,provider,element):
        if len(self._fetchedCovers[element]) == 0:
            message = self.tr("Could not fetch any cover for {}").format(element.getTitle())
            self._handleProviderError(provider,message)
        elif len(self._fetchedCovers[element]) == 1:
            # Only set the cover automatically if there is no UndoCommand on the stack.
            # Usually this isn't a big limitation because providers are queried at the beginning and finish
            # before the user has time to do something.
            if self.currentCovers[element] is None and self.stack.count() == 0:
                self._setCover(element,self._fetchedCovers[element][0])
                
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
        
    def getCover(self,element):
        return self.currentCovers[element]
    
    def setCover(self,cover):
        if cover != self.currentCovers[self.currentElement]:
            command = CoverUndoCommand(self,self.currentElement,cover)
            self.stack.push(command)
    
    def _setCover(self,element,cover):
        if cover != self.currentCovers[element]:
            self.currentCovers[element] = cover
            self.coverChanged.emit(element)
            if element == self.currentElement:
                self.currentCoverChanged.emit()
        
    def removeCover(self):
        self.setCover(None)
        
    def reset(self):
        self.stack.beginMacro(self.tr("Reset"))
        for element in self.elements:
            path = element.getCoverPath()
            if path is None:
                cover = None
            else: cover = Cover(path)
        
            if cover != self.currentCovers[element]:
                command = CoverUndoCommand(self,element,cover)
                self.stack.push(command)
        
        self.stack.endMacro()


class ErrorPanel(QtGui.QTextEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        
    def add(self,message):
        self.append(message)
        if not self.isVisible():
            self.setVisible(True)
        
        
class CoverDialog(QtGui.QDialog):
    def __init__(self,parent,level,elids):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Edit covers"))
        
        self.model = CoverDialogModel(QtGui.QUndoStack(),level,elids)
        self.model.providerStatusChanged.connect(self._handleProviderStatusChanged)
        self.model.availableCoversChanged.connect(self._fillAvailableCovers)
        self.model.currentCoverChanged.connect(self._handleCurrentCoverChanged)
        self.model.coverChanged.connect(self._handleCoverChanged)
                
        style = QtGui.QApplication.style()
        
        self.setLayout(QtGui.QVBoxLayout())
        splitter = QtGui.QSplitter(Qt.Vertical)
        self.layout().addWidget(splitter)
        
        topWidget = QtGui.QWidget()
        splitter.addWidget(topWidget)
        layout = QtGui.QHBoxLayout(topWidget)
        
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
        openFromURLButton.clicked.connect(self._handleOpenFromUrl)
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
        
        # Error panel
        self.errorPanel = ErrorPanel()
        splitter.addWidget(self.errorPanel)
        self.errorPanel.setVisible(False)
        self.model.error.connect(self.errorPanel.add)
        
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
        resetButton.clicked.connect(self.model.reset)
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
            cover = self.model.getCover(element)
            if cover is not None:
                item.setIcon(QtGui.QIcon(cover.pixmap))
            self.elementList.addItem(item)
        #self.elementList.setCurrentItem(self.elementList.item(0)) # will call setElement
        
        self.model.startFetchingCovers()
        self._fillAvailableCovers()
        self._handleCurrentCoverChanged()
        
    def _handleProviderStatusChanged(self):
        for provider,button in self.providerButtons.items():
            button.setEnabled(self.model.currentElement not in self.model._fetchedCovers)
    
    def _fillAvailableCovers(self):
        self.coverList.clear()
        for cover in self.model.availableCovers[self.model.currentElement]:
            pixmap = cover.pixmap
            item = QtGui.QListWidgetItem()
            text = "{}x{}".format(pixmap.width(),pixmap.height())
            if cover.text is not None:
                text = text + '\n' + cover.text
            item.setText(text)
            item.setIcon(QtGui.QIcon(pixmap))
            item.setData(Qt.UserRole,cover)
            if cover.path is not None:
                item.setData(Qt.ToolTipRole,cover.path)
            self.coverList.addItem(item)
            if cover == self.model.getCover(self.model.currentElement):
                item.setSelected(True)
                self.coverList.setCurrentItem(item)
    
    def _handleCoverChanged(self,element):
        for i in range(self.elementList.count()):
            item = self.elementList.item(i)
            if item.data(Qt.UserRole) == element:
                cover = self.model.getCover(element)
                if cover is not None:
                    item.setIcon(QtGui.QIcon(cover.pixmap))
                else: item.setIcon(QtGui.QIcon())
                break
            
    def _handleCurrentCoverChanged(self):    
        element = self.model.currentElement
        currentCover = self.model.getCover(element)
        if currentCover is not None:
            pixmap = currentCover.pixmap
            if pixmap.width() > BIG_COVER_SIZE or pixmap.height() > BIG_COVER_SIZE:
                pixmap = pixmap.scaled(BIG_COVER_SIZE,BIG_COVER_SIZE,transformMode=Qt.SmoothTransformation)
            self.label.setPixmap(pixmap)
        else: self.label.setPixmap(QtGui.QPixmap())
        
        for i in range(self.coverList.count()):
            item = self.coverList.item(i)
            cover = item.data(Qt.UserRole)
            if cover == currentCover:
                item.setSelected(True)
                self.coverList.setCurrentItem(item)
            else: item.setSelected(False)
            
        self.removeCoverButton.setEnabled(element.hasCover())
    
    def _handleElementSelected(self,current,previous):
        self.model.setElement(current.data(Qt.UserRole))
                
    def _handleCoverSelected(self):
        selectedItems = self.coverList.selectedItems()
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
            QtGui.QMessageBox.warning(self,self.tr("Failed to open the file"),
                                      self.tr("The file could not be opened."))
        else:
            cover = Cover(pixmap=pixmap)
            self.model.setCover(cover)
            self.model.addAvailableCovers({self.model.currentElement: [cover]})
        
    def _handleOpenFromUrl(self):
        url,ok = QtGui.QInputDialog.getText(self,self.tr("Open cover URL"),
                                            self.tr("Please enter the URL of the cover:"))
        if not ok: # user canceled the dialog
            return
        
        url = QtCore.QUrl.fromUserInput(url)
        if not url.isValid():
            QtGui.QMessageBox.warning(self,self.tr("Invalid URL"),
                                      self.tr("The specified URL is invalid."))
            return
        
        reply = application.network.get(QtNetwork.QNetworkRequest(url))
        reply.finished.connect(functools.partial(self._handleURLReplyFinished,reply))
        reply.error.connect(functools.partial(self._handleURLReplyError,reply))
        
    def _handleURLReplyFinished(self,reply):
        if reply.error() != QtNetwork.QNetworkReply.NoError:
            return 
        pixmap = QtGui.QPixmap()
        if not pixmap.loadFromData(reply.readAll()):
            url = reply.request().url().toString()
            QtGui.QMessageBox.warning(self,self.tr("Invalid image"),
                                      self.tr("Could not load cover image from '{}'.").format(url))
        else:
            cover = Cover(pixmap=pixmap)
            self.model.setCover(cover)
            self.model.addAvailableCovers({self.model.currentElement: [cover]})

    def _handleURLReplyError(self,reply,code):
        QtGui.QMessageBox.warning(self,self.tr("Network error"),
                                  self.tr("A network error appeared: ")+reply.errorString())
                          
    def _handleProviderButton(self,coverProvider):
        coverProvider.fetch([self.model.currentElement])
                