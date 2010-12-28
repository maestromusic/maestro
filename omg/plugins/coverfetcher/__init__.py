#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
import os.path
import urllib.request,urllib.parse,xml.dom.minidom, urllib.error
import webbrowser
import itertools

from PyQt4 import QtCore,QtGui,QtNetwork
from PyQt4.QtCore import Qt

from omg import covers, constants, models, tags
from omg.config import options
from omg.gui import formatter, treeview

LASTFM_API_KEY = 'b25b959554ed76058ac220b7b2e0a026'

def enable():
    treeview.contextMenuProviders['playlist'].append(contextMenuProvider)
    
def disable():
    treeview.contextMenuProviders['playlist'].remove(contextMenuProvider)

def contextMenuProvider(playlist,actions,currentIndex):
    """Provides an action for the playlist's context menu (confer playlist.contextMenuProvider). The action will only be enabled if at least one album is selected and in this case open a CoverFetcher-dialog for the selected albums."""
    action = QtGui.QAction("Cover holen...",playlist)
    elements = [element for element in playlist.getSelectedNodes() if isinstance(element,models.Element)]
    if len(elements) == 0:
        action.setEnabled(False)
    else: action.triggered.connect(lambda: CoverFetcher(QtGui.QApplication.activeWindow(),elements).open())
    actions.append(action)


class CoverData:
    def __init__(self,cover,text):
        coverSize = options.gui.cover_fetcher_cover_size
        self.cover = cover
        self.text = text
        if cover.width() > coverSize or cover.height() > coverSize:
            self.scaled = cover.scaled(coverSize,coverSize,Qt.KeepAspectRatio,Qt.SmoothTransformation)
        else: self.scaled = self.cover


class CoverFetcher(QtGui.QDialog):
    def __init__(self,parent,elements):
        QtGui.QWidget.__init__(self,parent)
        self.setWindowTitle("Cover holen")
        
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
        coverSize = options.gui.cover_fetcher_cover_size
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
        self.prevButton = QtGui.QPushButton(QtGui.QIcon("images/icons/go-previous.png"),"",self)
        self.prevButton.setEnabled(False)
        self.prevButton.clicked.connect(self.previous)
        bottomLeftLayout.addWidget(self.prevButton)
        self.numberLabel = QtGui.QLabel(self)
        bottomLeftLayout.addWidget(self.numberLabel)
        self.nextButton = QtGui.QPushButton(QtGui.QIcon("images/icons/go-next.png"),"",self)
        self.nextButton.setEnabled(False)
        self.nextButton.clicked.connect(self.next)
        bottomLeftLayout.addWidget(self.nextButton)
        bottomLeftLayout.addStretch(1)
        
        self.detailViewLabel = QtGui.QLabel(self)
        rightLayout.addWidget(self.detailViewLabel)
        
        bottomRightLayout1 = QtGui.QHBoxLayout()
        rightLayout.addLayout(bottomRightLayout1)
        
        coverFetchButton = QtGui.QPushButton("Cover von Last.fm holen",self)
        coverFetchButton.clicked.connect(self._handleLastFMCoverButton)
        bottomRightLayout1.addWidget(coverFetchButton)
        lastfmLabel = LastFmLabel(self)
        bottomRightLayout1.addWidget(lastfmLabel)
        
        bottomRightLayout2 = QtGui.QHBoxLayout()
        rightLayout.addLayout(bottomRightLayout2)
        
        customCoverButton = QtGui.QPushButton("Eigenes Cover laden...",self)
        customCoverButton.clicked.connect(self._handleCustomCoverButton)
        bottomRightLayout2.addWidget(customCoverButton)
        urlCoverButton = QtGui.QPushButton("URL öffnen...",self)
        urlCoverButton.clicked.connect(self._handleUrlCoverButton)
        bottomRightLayout2.addWidget(urlCoverButton)
        
        bottomRightLayout3 = QtGui.QHBoxLayout()
        rightLayout.addLayout(bottomRightLayout3)
        
        self.skipButton = QtGui.QPushButton("Überspringen",self)
        self.skipButton.clicked.connect(self.nextElement)
        bottomRightLayout3.addWidget(self.skipButton)
        self.saveButton = QtGui.QPushButton("Cover speichern",self)
        self.saveButton.clicked.connect(self.save)
        bottomRightLayout3.addWidget(self.saveButton)
        cancelButton = QtGui.QPushButton("Abbrechen",self)
        bottomRightLayout3.addWidget(cancelButton)
        cancelButton.clicked.connect(self.reject)
        
        rightLayout.addStretch(1)
        
        # Jump to the first element and initialize the gui
        self.nextElement()
    
    def _handleCustomCoverButton(self):
        fileName = QtGui.QFileDialog.getOpenFileName(self,"Cover öffnen",os.path.expanduser("~"),
                                                     "Bilddateien (*.png *.jpg *.bmp);;Alle Dateien (*)");
        if fileName == "": # user cancelled the dialog
            return
        
        image = QtGui.QPixmap(fileName)
        if image.isNull():
            QtGui.QMessageBox(QtGui.QMessageBox.Warning,"Fehler beim Öffnen der Datei",
                              "Die Datei konnte nicht geöffnet werden.",QtGui.QMessageBox.Ok,self).exec_()
        else:
            self.addImage(image,fileName)
            self.setPosition(len(self.coverData)-1)
    
    def _handleUrlCoverButton(self):
        url,ok = QtGui.QInputDialog.getText(self,"URL öffnen","Geben Sie die URL des Covers ein:")
        if not ok:
            return
        url = QtCore.QUrl(url)
        if not url.isValid():
            QtGui.QMessageBox(QtGui.QMessageBox.Warning,"Ungültige URL",
                              "Die eingegebene URL ist ungültig.",QtGui.QMessageBox.Ok,self).exec_()
        else: self.loadFromUrl(url,url.toString())
    
    def _handleLastFMCoverButton(self):
        urls = []
        element = self.elements[self.elementIndex]
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
            QtGui.QMessageBox(QtGui.QMessageBox.Warning,"Fehler während der Coverabfrage",
                              "Beim Abfragen des Covers ist ein Fehler aufgetreten. Vielleicht hat last.fm kein Cover"
                            +" für dieses Album. Oder die Netzwerkverbindung funktioniert nicht.",QtGui.QMessageBox.Ok,self).exec_()
        else:
            for url in urls:
                self.loadFromUrl(QtCore.QUrl(url),"Cover von last.fm")

    def loadFromUrl(self,url,text):
        if self.requestId is not None:
            return
        http = QtNetwork.QHttp(self)
        http.setHost(url.host())
        http.requestFinished.connect(lambda id,error: self._httpRequestFinished(text,buffer,id,error),
                                     Qt.QueuedConnection) # for some reason 
        buffer = QtCore.QBuffer()
        buffer.open(QtCore.QIODevice.WriteOnly)
        self.requestId = http.get(url.path(),buffer)

    def _httpRequestFinished(self,text,buffer,id,error):
        # For some reason Qt fires this event twice, the first time with another requestId. I have no idead where that requestId comes from...
        if id != self.requestId: 
            return
        
        if not error:
            self.requestId = None
            image = QtGui.QPixmap()
            if image.loadFromData(buffer.buffer()):
                self.addImage(image,text)
                self.setPosition(len(self.coverData)-1)
                return
        QtGui.QMessageBox(QtGui.QMessageBox.Warning,"Laden des Covers fehlgeschlagen",
                          "Das Laden des Covers ist fehlgeschlagen.",QtGui.QMessageBox.Ok,self).exec_()
    
    def addImage(self,image,text):
        assert(isinstance(image,QtGui.QPixmap))
        text = "{0} - {1}x{2} Pixel".format(text,image.width(),image.height())
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
            self.detailViewLabel.setText(formatter.HTMLFormatter(element).detailView())
            self.skipButton.setEnabled(self.elementIndex != len(self.elements) - 1)
            self.clear()
            if element.hasCover():
                self.addImage(QtGui.QPixmap(covers.getCoverPath(element.id)),"Vorheriges Cover")
        else: self.close()
        
    def save(self):
        assert len(self.coverData) > 0
        element = self.elements[self.elementIndex]
        if element.hasCover():
            if QtGui.QMessageBox(QtGui.QMessageBox.Question,"Datei überschreiben?",
                                 "Soll das vorhandene Cover überschrieben werden?",
                                 QtGui.QMessageBox.Yes|QtGui.QMessageBox.No,self).exec_() \
                     != QtGui.QMessageBox.Yes:
                return
        if not covers.setCover(element.id,self.coverData[self.position].cover):
            QtGui.QMessageBox(QtGui.QMessageBox.Warning,"Speichern fehlgeschlagen",
                              "Das Cover konnte nicht gespeichert werden.",
                              QtGui.QMessageBox.Ok,self).exec_()
        else:
            self.nextElement()
        

class LastFmLabel(QtGui.QLabel):
    def __init__(self,parent):
        QtGui.QLabel.__init__(self,parent)
        self.setPixmap(QtGui.QPixmap(constants.IMAGES+"lastfm.gif"))
        self.setCursor(Qt.PointingHandCursor)
        
    def mouseReleaseEvent(self,event):
        webbrowser.open("http://www.lastfm.de")
        return True
