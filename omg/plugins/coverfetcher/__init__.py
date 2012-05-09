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

import os.path
import urllib.request,urllib.parse,xml.dom.minidom, urllib.error
import webbrowser
import itertools

from PyQt4 import QtCore,QtGui,QtNetwork
from PyQt4.QtCore import Qt

from ... import covers, config
from ...core import tags
from ...modify import treeactions

translate = QtGui.QApplication.translate

LASTFM_API_KEY = 'b25b959554ed76058ac220b7b2e0a026'


def defaultConfig():
    return {"coverfetcher": {
            "cover_size": (int,400,"Cover size in the coverfetcher.")
        }}
    

def enable():
    from ...gui import browser, editor, playlist
    for tree in (browser.BrowserTreeView,editor.EditorTreeView,playlist.PlaylistTreeView):
        tree.actionConfig.addActionDefinition( ((translate(__name__,"plugins"), "fetchcover"),),
                                               CoverFetcherAction)
    
    
def disable():
    from ...gui import browser, editor, playlist
    for tree in (browser.BrowserTreeView,editor.EditorTreeView,playlist.PlaylistTreeView):
        tree.actionConfig.removeActionDefinition( ((translate(__name__,"plugins"), "fetchcover"),))
    

class CoverFetcherAction(treeactions.TreeAction):
    """Action to edit tags; exists both in a recursive and non-recursive variant, depending on the argument
    to the constructor."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.setText(self.tr('Fetch cover...'))
    
    def initialize(self):
        self.setEnabled(self.parent().nodeSelection.hasElements())
    
    def doAction(self):
        """Open a dialog to edit the tags of the currently selected elements (and the children, if
        *recursive* is True). This is called by the edit tags actions in the contextmenu.
        """
        elements = self.parent().nodeSelection.elements(False)
        CoverFetcher(QtGui.QApplication.activeWindow(),elements).open()
        

class CoverData:
    def __init__(self,cover,text):
        coverSize = config.options.coverfetcher.cover_size
        self.cover = cover
        self.text = text
        if cover.width() > coverSize or cover.height() > coverSize:
            self.scaled = cover.scaled(coverSize,coverSize,Qt.KeepAspectRatio,Qt.SmoothTransformation)
        else: self.scaled = self.cover


class CoverFetcher(QtGui.QDialog):
    def __init__(self,parent,elements):
        QtGui.QWidget.__init__(self,parent)
        self.setWindowTitle(self.tr("Add cover"))
        
        assert len(elements) >= 1
        self.elements = elements
        self.elementIndex = -1 # self.nextElement will be called at the end of this constructor
        self.coverData = []
        self.position = None
        self.requestId = None
        
        # Create GUI
        layout = QtGui.QHBoxLayout()
        self.setLayout(layout)
        
        leftLayout = QtGui.QVBoxLayout()
        layout.addLayout(leftLayout)
        rightLayout = QtGui.QVBoxLayout()
        layout.addLayout(rightLayout)
        
        self.imageLabel = QtGui.QLabel(self)
        coverSize = config.options.coverfetcher.cover_size
        self.imageLabel.setMinimumSize(coverSize+2,coverSize+2) # two pixels for the border
        self.imageLabel.setSizePolicy(QtGui.QSizePolicy.Fixed,QtGui.QSizePolicy.Fixed)
        self.imageLabel.setAlignment(Qt.AlignLeft|Qt.AlignTop)
        self.imageLabel.setFrameStyle(QtGui.QFrame.Box)
        leftLayout.addWidget(self.imageLabel)
    
        self.textLabel = QtGui.QLabel(self)
        self.textLabel.setSizePolicy(QtGui.QSizePolicy.Fixed,QtGui.QSizePolicy.Minimum)
        self.textLabel.setMinimumWidth(coverSize+2) # two pixels for the border of self.imageLabel
        self.textLabel.setMaximumWidth(coverSize+2)
        self.textLabel.setTextFormat(Qt.PlainText)
        self.textLabel.setWordWrap(True)
        leftLayout.addWidget(self.textLabel)
        
        bottomLeftLayout = QtGui.QHBoxLayout()
        leftLayout.addLayout(bottomLeftLayout)
        
        bottomLeftLayout.addStretch(1)
        self.prevButton = QtGui.QPushButton(QtGui.QIcon(":omg/icons/go-previous.png"),"",self)
        self.prevButton.setEnabled(False)
        self.prevButton.clicked.connect(self.previous)
        bottomLeftLayout.addWidget(self.prevButton)
        self.numberLabel = QtGui.QLabel(self)
        bottomLeftLayout.addWidget(self.numberLabel)
        self.nextButton = QtGui.QPushButton(QtGui.QIcon(":omg/icons/go-next.png"),"",self)
        self.nextButton.setEnabled(False)
        self.nextButton.clicked.connect(self.next)
        bottomLeftLayout.addWidget(self.nextButton)
        bottomLeftLayout.addStretch(1)
        
        self.detailViewLabel = QtGui.QLabel(self)
        rightLayout.addWidget(self.detailViewLabel)
        
        bottomRightLayout1 = QtGui.QHBoxLayout()
        rightLayout.addLayout(bottomRightLayout1)
        
        coverFetchButton = QtGui.QPushButton(self.tr("Fetch cover from Last.fm"),self)
        coverFetchButton.clicked.connect(self._handleLastFMCoverButton)
        bottomRightLayout1.addWidget(coverFetchButton)
        lastfmLabel = LastFmLabel(self)
        bottomRightLayout1.addWidget(lastfmLabel)
        
        bottomRightLayout2 = QtGui.QHBoxLayout()
        rightLayout.addLayout(bottomRightLayout2)
        
        customCoverButton = QtGui.QPushButton(self.tr("Load image file..."),self)
        customCoverButton.clicked.connect(self._handleCustomCoverButton)
        bottomRightLayout2.addWidget(customCoverButton)
        urlCoverButton = QtGui.QPushButton(self.tr("Open URL..."),self)
        urlCoverButton.clicked.connect(self._handleUrlCoverButton)
        bottomRightLayout2.addWidget(urlCoverButton)
        
        bottomRightLayout3 = QtGui.QHBoxLayout()
        rightLayout.addLayout(bottomRightLayout3)
        
        self.skipButton = QtGui.QPushButton(self.tr("Skip"),self)
        self.skipButton.clicked.connect(self.nextElement)
        bottomRightLayout3.addWidget(self.skipButton)
        self.saveButton = QtGui.QPushButton(self.tr("Save cover"),self)
        self.saveButton.clicked.connect(self.save)
        bottomRightLayout3.addWidget(self.saveButton)
        cancelButton = QtGui.QPushButton(self.tr("Cancel"),self)
        bottomRightLayout3.addWidget(cancelButton)
        cancelButton.clicked.connect(self.reject)
        
        rightLayout.addStretch(1)
        
        # Jump to the first element and initialize the gui
        self.nextElement()
    
    def _handleCustomCoverButton(self):
        fileName = QtGui.QFileDialog.getOpenFileName(self,self.tr("Open cover file"),os.path.expanduser("~"),
                                                     self.tr("Image files (*.png *.jpg *.bmp);;All files (*)"))
        if fileName == "": # user cancelled the dialog
            return
        
        image = QtGui.QPixmap(fileName)
        if image.isNull():
            QtGui.QMessageBox(QtGui.QMessageBox.Warning,self.tr("Failed to open the file"),
                              self.tr("The file could not be opened."),QtGui.QMessageBox.Ok,self).exec_()
        else:
            self.addImage(image,fileName)
            self.setPosition(len(self.coverData)-1)
    
    def _handleUrlCoverButton(self):
        url,ok = QtGui.QInputDialog.getText(self,self.tr("Open URL"),self.tr("Please enter the cover's URL:"))
        if not ok:
            return
        url = QtCore.QUrl(url)
        if not url.isValid():
            QtGui.QMessageBox(QtGui.QMessageBox.Warning,self.tr("Invalid URL"),
                              self.tr("The given URL is invalid."),QtGui.QMessageBox.Ok,self).exec_()
        else: self.loadFromUrl(url,url.toString())
    
    def _handleLastFMCoverButton(self):
        element = self.elements[self.elementIndex]
        if tags.get("artist") not in element.tags or tags.ALBUM not in element.tags:
            QtGui.QMessageBox.warning(self,self.tr("Missing tag"),
                              self.tr("I need an artist tag and an album tag to fetch covers."))
            return
                              
        urls = []
        for artist,album in itertools.product(element.tags[tags.get("artist")],element.tags[tags.ALBUM]):
            try:
                lastFMUrl = 'http://ws.audioscrobbler.com/2.0/?method=album.getinfo&artist={0}&album={1}&api_key={2}'\
                            .format(urllib.parse.quote(artist),urllib.parse.quote(album),LASTFM_API_KEY)
                document = xml.dom.minidom.parseString(urllib.request.urlopen(lastFMUrl).read())
                lfm = document.firstChild
                if lfm.getAttribute('status') != 'ok':
                    continue
                for albumNode in lfm.childNodes:
                    if isinstance(albumNode,xml.dom.minidom.Element) and albumNode.tagName == 'album':
                        for node in albumNode.childNodes:
                            if isinstance(node,xml.dom.minidom.Element) and node.tagName == 'image'\
                                    and node.getAttribute('size') == 'extralarge' and node.firstChild != None:
                                urls.append(node.firstChild.data)
            except urllib.error.URLError:
                pass # The error message below will be displayed
                
        if len(urls) == 0:
            QtGui.QMessageBox(QtGui.QMessageBox.Warning,self.tr("Failed to fetch cover"),
                              self.tr("An error occurred during fetching the cover. Maybe Last.fm does not have a cover for this album. Or there was an error with the connection."),
                              QtGui.QMessageBox.Ok,self).exec_()
        else:
            for url in urls:
                self.loadFromUrl(QtCore.QUrl(url),self.tr("Cover from Last.fm"))

    def loadFromUrl(self,url,text):
        if self.requestId is not None:
            return
        http = QtNetwork.QHttp(self)
        http.setHost(url.host())
        http.requestFinished.connect(lambda id,error: self._httpRequestFinished(text,buffer,id,error),
                                     Qt.QueuedConnection)
        buffer = QtCore.QBuffer()
        buffer.open(QtCore.QIODevice.WriteOnly)
        self.requestId = http.get(url.path(),buffer)

    def _httpRequestFinished(self,text,buffer,id,error):
        # For some reason Qt fires this event twice, the first time with another requestId. I have no idea where that requestId comes from...
        if id != self.requestId: 
            return
        
        if not error:
            self.requestId = None
            image = QtGui.QPixmap()
            if image.loadFromData(buffer.buffer()):
                self.addImage(image,text)
                self.setPosition(len(self.coverData)-1)
                return
        QtGui.QMessageBox(QtGui.QMessageBox.Warning,self.tr("Loading cover failed"),
                          self.tr("The cover could not be loaded."),QtGui.QMessageBox.Ok,self).exec_()
    
    def addImage(self,image,text):
        assert(isinstance(image,QtGui.QPixmap))
        text = "{0} - {1}x{2} {3}".format(text,image.width(),image.height(),self.tr("pixel"))
        self.coverData.append(CoverData(image,text))
        if self.position is None:
            self.setPosition(0)
            self.nextButton.setEnabled(True)
            self.prevButton.setEnabled(True)
            self.saveButton.setEnabled(True)
        self.numberLabel.setText("{0}/{1}".format(self.position+1,len(self.coverData)))
        self.adjustSize()
        
    def setPosition(self,position):
        self.position = position
        if position is not None:
            self.imageLabel.setPixmap(self.coverData[position].scaled)
            self.textLabel.setText(self.coverData[position].text)
            self.numberLabel.setText("{0}/{1}".format(self.position+1,len(self.coverData)))
        
    def next(self):
        if self.position is not None:
            self.setPosition((self.position + 1) % len(self.coverData))
    
    def previous(self):
        if self.position is not None:
            self.setPosition((self.position - 1) % len(self.coverData))
    
    def clear(self):
        self.coverData = []
        self.nextButton.setEnabled(False)
        self.prevButton.setEnabled(False)
        self.saveButton.setEnabled(False)
        self.imageLabel.setPixmap(QtGui.QPixmap())
        self.textLabel.setText("")
        self.numberLabel.setText("")
        self.setPosition(None)
        
    def nextElement(self):
        if self.elementIndex < len(self.elements) - 1:
            self.elementIndex = self.elementIndex + 1
            element = self.elements[self.elementIndex]
            #self.detailViewLabel.setText(formatter.HTMLFormatter(element).detailView())
            self.skipButton.setEnabled(self.elementIndex != len(self.elements) - 1)
            self.clear()
            if element.hasCover():
                self.addImage(QtGui.QPixmap(covers.getCoverPath(element.id)),self.tr("Previous cover"))
        else: self.close()
        
    def save(self):
        assert len(self.coverData) > 0
        element = self.elements[self.elementIndex]
        if element.hasCover():
            if QtGui.QMessageBox(QtGui.QMessageBox.Question,self.tr("Overwrite file?"),
                                 self.tr("Should the existing cover be overriden?"),
                                 QtGui.QMessageBox.Yes|QtGui.QMessageBox.No,self).exec_() \
                     != QtGui.QMessageBox.Yes:
                return
        covers.setCover(element.id,self.coverData[self.position].cover)
        self.nextElement()
        

class LastFmLabel(QtGui.QLabel):
    def __init__(self,parent):
        QtGui.QLabel.__init__(self,parent)
        self.setPixmap(QtGui.QPixmap(":omg/lastfm.gif"))
        self.setCursor(Qt.PointingHandCursor)
        
    def mouseReleaseEvent(self,event):
        webbrowser.open("http://www.lastfm.de")
        return True
