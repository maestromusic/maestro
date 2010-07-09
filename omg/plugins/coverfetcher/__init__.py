#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
import os.path
import webbrowser

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

from omg import covers, config, constants, models
from omg.gui import formatter, playlist

def enable():
    playlist.contextMenuProvider.append(getMenuEntries)
    
def disable():
    playlist.contextMenuProvider.remove(getMenuEntries)

def getMenuEntries(playlist,node):
    """Provides an action for the playlist's context menu (confer playlist.contextMenuProvider). The action will only be enabled if at least one album is selected and in this case open a CoverFetcher-dialog for the selected albums."""
    action = QtGui.QAction("Cover holen...",playlist)
    elements = [playlist.model().data(index) for index in playlist.selectedIndexes()]
    if len(elements) == 0:
        action.setEnabled(False)
    else: action.triggered.connect(lambda: CoverFetcher(QtGui.QApplication.activeWindow(),elements).open())
    return [action]


class CoverFetcher(QtGui.QDialog):
    def __init__(self,parent,elements):
        QtGui.QWidget.__init__(self,parent)
        self.setWindowTitle("Cover holen")
        
        assert len(elements) >= 1
        self.elements = elements
        self.elementIndex = -1 # self.nextElement will be called at the end of this constructor
        self.covers = []
        self.texts = []
        self.position = None
        
        # Create GUI
        layout = QtGui.QHBoxLayout()
        self.setLayout(layout)
        
        leftLayout = QtGui.QVBoxLayout()
        layout.addLayout(leftLayout)
        rightLayout = QtGui.QVBoxLayout()
        layout.addLayout(rightLayout)
        
        self.imageLabel = QtGui.QLabel(self)
        coverSize = config.get("gui","cover_fetcher_cover_size")
        self.imageLabel.setMinimumSize(coverSize,coverSize)
        self.imageLabel.setScaledContents(True)
        self.imageLabel.setFrameStyle(QtGui.QFrame.Box)
        leftLayout.addWidget(self.imageLabel)
    
        self.textLabel = QtGui.QLabel(self)
        self.textLabel.setMaximumWidth(coverSize)
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
        
        self.coverFetchButton = QtGui.QPushButton("Cover von Last.fm holen",self)
        bottomRightLayout1.addWidget(self.coverFetchButton)
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
                              "Die Datei konnte nicht geöffnet werden.",QtGui.QMessageBox.Ok,self)\
                                .exec_()
        else:
            self.addImage(image,"{0} - {1}x{2} Pixel".format(fileName,image.size().width(),image.size().height()))
            self.setPosition(len(self.covers)-1)
    
    def _handleUrlCoverButton(self):
        url = QtGui.QInputDialog.getText(self,"URL öffnen","Geben Sie die URL des Covers ein:")
        #~ QUrl url("http://mydomain.com/images/image.jpg";);
#~ http = new QHttp(this);
#~ connect(http, SIGNAL(requestFinished(int, bool)),this, SLOT(Finished(int, 
#~ bool)));
#~ buffer = new QBuffer(&bytes);
#~ buffer->open(QIODevice::WriteOnly);
#~ http->setHost(url.host());
#~ Request=http->get (url.path(),buffer);

        
    def addImage(self,image,text):
        self.covers.append(image)
        self.texts.append(text)
        if self.position is None:
            self.setPosition(0)
            self.nextButton.setEnabled(True)
            self.prevButton.setEnabled(True)
            self.saveButton.setEnabled(True)
        
    def setPosition(self,position):
        self.position = position
        if position is not None:
            self.imageLabel.setPixmap(self.covers[position])
            self.textLabel.setText(self.texts[position])
            self.numberLabel.setText("{0}/{1}".format(self.position+1,len(self.covers)))
        
    def next(self):
        if self.position is not None:
            self.setPosition((self.position + 1) % len(self.covers))
    
    def previous(self):
        if self.position is not None:
            self.setPosition((self.position - 1) % len(self.covers))
    
    def clear(self):
        self.covers = []
        self.texts = []
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
            self.detailViewLabel.setText(formatter.HTMLFormatter(self.elements[self.elementIndex]).detailView())
            self.skipButton.setEnabled(self.elementIndex != len(self.elements) - 1)
            self.clear()
        else: self.close()
        
    def save(self):
        assert len(self.covers) > 0
        element = self.elements[self.elementIndex]
        if element.hasCover():
            if QtGui.QMessageBox(QtGui.QMessageBox.Question,"Datei überschreiben?",
                                 "Soll das vorhandene Cover überschrieben werden?",
                                 QtGui.QMessageBox.Yes|QtGui.QMessageBox.No,self).exec_() \
                     != QtGui.QMessageBox.Yes:
                return
        if not covers.setCover(element.id,self.covers[self.position]):
            QtGui.QMessageBox(QtGui.QMessageBox.Warning,"Speichern fehlgeschlagen",
                              "Das Cover konnte nicht gespeichert werden.",
                              QtGui.QMessageBox.Ok,self).exec_()
        else: self.nextElement()
        

class LastFmLabel(QtGui.QLabel):
    def __init__(self,parent):
        QtGui.QLabel.__init__(self,parent)
        self.setPixmap(QtGui.QPixmap(constants.IMAGES+"lastfm.gif"))
        self.setCursor(Qt.PointingHandCursor)
        
    def mouseReleaseEvent(self,event):
        webbrowser.open("http://www.lastfm.de")
        return True