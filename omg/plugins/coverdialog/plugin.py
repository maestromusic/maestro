# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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

translate = QtCore.QCoreApplication.translate

from ...core import covers
from ...core.elements import Element
from ...gui import treeactions
from ...gui.misc import busyindicator
from ... import application, stack

# Various cover sizes used in the dialog
BIG_COVER_SIZE = 400
AVAILABLE_COVER_SIZE = 100
SMALL_COVER_SIZE = 40


def enable():
    from omg.gui import editor, browser
    editor.EditorTreeView.actionConfig.addActionDefinition((("plugins", 'covers'),), CoverAction)
    browser.BrowserTreeView.actionConfig.addActionDefinition((("plugins", 'covers'),), CoverAction)
        
def disable():
    from omg.gui import editor, browser
    editor.EditorTreeView.actionConfig.removeActionDefinition((("plugins", 'covers'),))
    browser.BrowserTreeView.actionConfig.removeActionDefinition((("plugins", 'covers'),))
    
    
class CoverAction(treeactions.TreeAction):
    """Action to open the CoverDialog with the currently selected elements."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setText(self.tr("Edit covers..."))
    
    def initialize(self, selection):
        self.setEnabled(selection.hasWrappers())
    
    def doAction(self):
        CoverDialog(self.parent(),
                    self.level(),
                    [wrap.element for wrap in self.parent().selection.wrappers()]).exec_()
            
            
class Cover:
    """The core stores covers simply by their paths (because it uses the data-table). This does not work
    in the CoverDialog since downloaded covers temporarily do not have a path. Thus this class is used
    which stores
    
        - a path (if present)
        - a pixmap
        - optionally a text
        
    Either *path* or *pixmap* must be given. If only *path* is given, the pixmap is loaded from that path.
    """
    def __init__(self,path=None,pixmap=None,text=None):
        if path is None and pixmap is None:
            raise ValueError("Either path or pixmap must not be None")
        self.path = path
        if pixmap is not None:
            self.pixmap = pixmap
        else: self.pixmap = QtGui.QPixmap(path)
        self.text = text
        
    def __eq__(self,other):
        if not isinstance(other,Cover): 
            return False
        if self.path is not None:
            return self.path == other.path
        else: return self is other
        
    def __ne__(self,other):
        return not self.__eq__(other)


class CoverUndoCommand:
    """UndoCommand that is internally used by the CoverDialog. It sets the cover of *element* in the
    CoverDialogModel *model* to *new* (which may be None)."""
    def __init__(self, model, element, new):
        super().__init__()
        self.text = translate("CoverUndoCommand", "change cover")
        self.model = model
        self.element = element
        self.old = model.getCover(element)
        self.new = new
        
    def redo(self):
        self.model._setCover(self.element,self.new)
        
    def undo(self):
        self.model._setCover(self.element,self.old)
        
        
class CoverDialogModel(QtCore.QObject):
    """Model that is used by the CoverDialog.
    
        - *level* is the level from which the elements are taken
        - *elements* the elements whose cover can be selected
    """
    
    # Emitted when the user has selected a different element.
    currentElementChanged = QtCore.pyqtSignal()
    # Emitted when the status of a cover provider at the current element has changed.
    providerStatusChanged = QtCore.pyqtSignal()
    # Emitted when the available covers for the current element have changed
    availableCoversChanged = QtCore.pyqtSignal()
    # Emitted when the current cover of an element has changed. The element is passed as argument.
    coverChanged = QtCore.pyqtSignal(Element)
    # Emitted when an error happens while loading a cover. The argument is an error message.
    error = QtCore.pyqtSignal(str)
    # Emitted when the busy-state changes. The argument states whether at least one provider is busy
    busyChanged = QtCore.pyqtSignal(bool)
    
    def __init__(self, level, elements, stack):
        super().__init__()
        self.level = level
        self.elements = elements
        self.stack = stack
        self.currentElement = self.elements[0]
                                 
        # Initialize covers
        self.availableCovers = {} # element -> list of all available covers (as Cover instances)
        self.currentCovers = {}   # element -> current cover or None
        self._fetchedCovers = {}  # element -> list of all covers that have been fetched from all providers
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
        """Start fetching covers from all cover providers for those elements that do not have a cover yet."""
        elementsWithoutCover = [element for element in self.elements if self.currentCovers[element] is None]
        if len(elementsWithoutCover) > 0:
            self.busyChanged.emit(True)
            for element in elementsWithoutCover:
                self._fetchedCovers[element] = []
            for coverProvider in self.coverProviders:
                coverProvider.fetch(elementsWithoutCover)
        
    def fetchCovers(self,coverProvider):
        """Fetch covers for the current element using the given cover provider."""
        self.busyChanged.emit(True)
        if self.currentElement not in self._fetchedCovers:
            self._fetchedCovers[self.currentElement] = []
        coverProvider.fetch([self.currentElement])
        
    def _handleProviderLoaded(self,provider,element,pixmap):
        """Handle the loaded-signal of cover providers."""
        if element is self.currentElement:
            self.providerStatusChanged.emit()
        cover = Cover(pixmap=pixmap,text=provider.name())
        self._fetchedCovers[element].append(cover)
        self.addAvailableCovers({element: [cover]})
    
    def _handleProviderError(self,provider,message):
        """Handle the error-signal of cover providers."""
        self.error.emit(self.tr("{}: {}").format(provider.name(),message))
        
    def _handleProviderFinished(self,provider,element):
        """Handle the finished-signal of cover providers."""
        if len(self._fetchedCovers[element]) == 0:
            message = self.tr("Could not fetch any cover for {}").format(element.getTitle())
            self._handleProviderError(provider,message)
        elif len(self._fetchedCovers[element]) == 1:
            # Only set the cover automatically if there is no UndoCommand on the stack.
            # Usually this isn't a big limitation because providers are queried at the beginning and finish
            # before the user has time to do something.
            if self.currentCovers[element] is None and self.stack.count() == 0:
                self._setCover(element,self._fetchedCovers[element][0])
        
        if all(not provider.isBusy() for provider in self.coverProviders):
            self.busyChanged.emit(False)
                  
    def addAvailableCovers(self,coverDict):
        """Add available covers. *coverDict* must map elements to lists of new covers (as instances of
        Cover)."""
        for element,covers in coverDict.items():
            self.availableCovers[element].extend(covers)
        if self.currentElement in coverDict:
            self.availableCoversChanged.emit()
         
    def setElement(self,element):
        """Set the current element."""
        if element != self.currentElement:
            self.currentElement = element
            self.currentElementChanged.emit()
        
    def getCover(self,element):
        """Return the current cover of *element* (may be None)."""
        return self.currentCovers[element]
    
    def setCover(self,cover):
        """Set the cover of the current element (undoable)."""
        if cover != self.currentCovers[self.currentElement]:
            command = CoverUndoCommand(self, self.currentElement,cover)
            self.stack.push(command)
    
    def _setCover(self,element,cover):
        """Set the cover of the given element (not undoable)."""
        if cover != self.currentCovers[element]:
            self.currentCovers[element] = cover
            self.coverChanged.emit(element)
        
    def removeCover(self):
        """Remove the cover of the current element (undoable)."""
        self.setCover(None)
        
    def reset(self):
        """Add a command to the dialog's stack that will reset all covers to the state of the underlying
        level."""
        self.stack.beginMacro(self.tr("Reset"))
        for element in self.elements:
            path = element.getCoverPath()
            if path is None:
                cover = None
            else: cover = Cover(path)
        
            if cover != self.currentCovers[element]:
                command = CoverUndoCommand(self, element,cover)
                self.stack.push(command)
        
        self.stack.endMacro()
        
    def save(self):
        """Add a command to the application's stack that will save the covers from the dialog to the
        underlying level."""
        covers = {}
        for element in self.elements:
            cover = self.currentCovers[element]
            if cover is not None:
                if cover.path is not None:
                    cover = cover.path
                else: cover = cover.pixmap
            covers[element] = cover
        
        self.level.setCovers(covers)
        
        
class CoverDialog(QtGui.QDialog):
    """A dialog that allows to change covers of some elements on the given level. The dialog will allow the
    user to load covers from files, urls or cover providers from the covers-module.
    """
    def __init__(self, parent, level, elements):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Edit covers"))
        
        self.stack = level.stack.createSubstack(modalDialog=True)
        self.model = CoverDialogModel(level, elements, self.stack)
        self.model.currentElementChanged.connect(self._handleCurrentElementChanged)
        self.model.providerStatusChanged.connect(self._handleProviderStatusChanged)
        self.model.availableCoversChanged.connect(self._fillAvailableCovers)
        self.model.coverChanged.connect(self._handleCoverChanged)
        # busyChanged is connected below
                
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
            button.clicked.connect(functools.partial(self.model.fetchCovers,coverProvider))
            self.providerButtons[coverProvider] = button
            coverButtonLayout.addWidget(button)
            
        coverButtonLayout.addStretch()
        
        busyLabel = busyindicator.BusyLabel(self.tr("Covers are\nbeing loaded"))
        self.model.busyChanged.connect(busyLabel.setRunning)
        coverButtonLayout.addWidget(busyLabel)
        
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
        commitButton.clicked.connect(self._handleOkButton)
        
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
        
        self.model.startFetchingCovers()
        self._fillAvailableCovers()
        self._updateCoverLabel()
        self.finished.connect(lambda _ : stack.closeSubstack(self.stack))
    
    def _fillAvailableCovers(self):
        """Fill the list of available covers with those of the current element."""
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
    
    def _handleCurrentElementChanged(self):
        """Handle changes of the current element (selected by the user."""
        # We do not need to update self.elementList, because that list provides the only way to change the
        # current element and thus is always correct.
        self._updateCoverLabel()
        self._fillAvailableCovers()
        self._handleProviderStatusChanged()
        self.removeCoverButton.setEnabled(self.model.getCover(self.model.currentElement) is not None)
        
    def _handleCoverChanged(self,element):
        """Handle cover changed signals from the model: Update the GUI."""
        for i in range(self.elementList.count()):
            item = self.elementList.item(i)
            if item.data(Qt.UserRole) == element:
                cover = self.model.getCover(element)
                if cover is not None:
                    item.setIcon(QtGui.QIcon(cover.pixmap))
                else: item.setIcon(QtGui.QIcon())
                break
        
        if element == self.model.currentElement:
            self._updateCoverLabel()
            
            for i in range(self.coverList.count()):
                item = self.coverList.item(i)
                cover = item.data(Qt.UserRole)
                if cover == self.model.getCover(element):
                    item.setSelected(True)
                    self.coverList.setCurrentItem(item)
                else: item.setSelected(False)
            
            self.removeCoverButton.setEnabled(self.model.getCover(element) is not None)
            
    def _updateCoverLabel(self):
        """Let the cover label display the cover of the current element."""
        element = self.model.currentElement
        currentCover = self.model.getCover(element)
        if currentCover is not None:
            pixmap = currentCover.pixmap
            if pixmap.width() > BIG_COVER_SIZE or pixmap.height() > BIG_COVER_SIZE:
                pixmap = pixmap.scaled(BIG_COVER_SIZE,BIG_COVER_SIZE,transformMode=Qt.SmoothTransformation)
            self.label.setPixmap(pixmap)
        else: self.label.setPixmap(QtGui.QPixmap())
        
    def _handleProviderStatusChanged(self):
        """Enable/disable the buttons for cover providers depending on whether the cover of the provider
        has already started (or even finished) to fetch the current element's cover."""
        for button in self.providerButtons.values():
            button.setEnabled(self.model.currentElement not in self.model._fetchedCovers)
    
    def _handleElementSelected(self,current,previous):
        """This is called when the user selects elements in the element list."""
        self.model.setElement(current.data(Qt.UserRole))
                
    def _handleCoverSelected(self):
        """This is called when the user selects a cover in the list of available covers."""
        selectedItems = self.coverList.selectedItems()
        if len(selectedItems) == 0:
            return # This happens due to self.coverList.clear in _fillAvailableCovers
        cover = selectedItems[0].data(Qt.UserRole)
        self.model.setCover(cover)
            
    def _handleOpenFromFile(self):
        """Handle the "Open from File..." button."""
        fileName = QtGui.QFileDialog.getOpenFileName(
                                self,
                                self.tr("Open cover file"),
                                os.path.expanduser("~"),
                                self.tr("Image files (*.png *.jpg *.jpeg *.bmp);;All files (*)"))
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
        """Handle the "Open from URL..." button."""
        clipTexts = [QtGui.qApp.clipboard().text(mode)
                     for mode in (QtGui.QClipboard.Selection, QtGui.QClipboard.Clipboard) ]
        dialogText = ""
        for text in clipTexts:
            if text.startswith("http") or text.startswith("www"):
                dialogText = text 
        url, ok = QtGui.QInputDialog.getText(self,self.tr("Open cover URL"),
                                            self.tr("Please enter the URL of the cover:"),
                                            QtGui.QLineEdit.Normal,
                                            dialogText)
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
        """This is called when a download request started with the "Open from URL..." button has finished.
        This is not used for cover providers."""
        if reply.error() != QtNetwork.QNetworkReply.NoError:
            # an error occurred and has been handled by _handleNetworkError
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
        """Handle errors from download requests started with the "Open from URL..." button."""
        self.errorPanel.add(self.tr("A network error appeared: {}").format(reply.errorString()))
        
    def _handleOkButton(self):
        """Handle the OK button."""
        self.model.save()
        self.accept()


class ErrorPanel(QtGui.QTextEdit):
    """QTextEdit that is used to display error messages from cover providers."""
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        
    def add(self,message):
        """Add *message* as new line and make this panel visible."""
        self.append(message)
        if not self.isVisible():
            self.setVisible(True)
                