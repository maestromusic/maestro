# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtCore, QtGui
from omg.gui.abstractdelegate import AbstractDelegate
import omg
from PyQt4.QtCore import Qt

class GopulateDelegate(AbstractDelegate):
    def __init__(self,parent = None):
        AbstractDelegate.__init__(self,parent)
        
    def layout(self, index):
        elem = index.internalPointer()
        if (isinstance(elem,omg.gopulate.models.GopulateContainer)):
            if "album" in elem.sameTags and "artist" in elem.sameTags:
                titleLine = '"{}" from {}'.format(", ".join(elem.tags['album']), ", ".join(elem.tags['artist']))
                if "date" in elem.sameTags:
                    titleLine += " ({})".format(", ".join(elem.tags['date']))
                self.addLine(titleLine)
            for k in elem.sameTags:
                if k == "album" or k == "artist" or k == "date":
                    continue
                for v in elem.tags[k]:
                    self.addLine("{}={}".format(k,v))
        elif (isinstance(elem,omg.gopulate.models.FileSystemFile)):
            if "title" in elem.tags:
                firstLine = ", ".join(elem.tags['title'])
                if "tracknumber" in elem.tags:
                    firstLine = "{:2} - ".format(", ".join(elem.tags['tracknumber'])) + firstLine
                self.addLine(firstLine)
            for k,vs in elem.tags.items():
                if k == "title" or k == "tracknumber":
                    continue
                if k in elem.parent.sameTags:
                    continue
                for v in vs:
                    self.addLine("{}={}".format(k,v))
        
class GopulateEditorWidget(QtGui.QLabel):
    def __init__(self, parent = None):
        QtGui.QWidget.__init__(self,parent)
        self.setText('<p> omgwtf? </p><br /><p><b>OMGWTF!?</b></p>')
        
    def setElement(self, cur, prev):
        self.element = cur.internalPointer()
        self.setText("\n".join("{}={}".format(k,v) for k,v in self.element.tags.items()))

class GopulatTreeWidget(QtGui.QTreeView):
    
    def __init__(self, parent = None):
        QtGui.QTreeView.__init__(self, parent)
        self.setItemDelegate(GopulateDelegate())
        self.setAlternatingRowColors(True)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)
        self.setSelectionMode(self.ExtendedSelection)

    def contextMenuEvent(self, event):
        print("context!")
        ac = QtGui.QAction("test",self)
        menu = QtGui.QMenu(self)
        menu.addAction(ac)
        menu.popup(event.globalPos())
        
class GopulateWidget(QtGui.QWidget):
    
    def __init__(self, model=None):
        QtGui.QWidget.__init__(self)
        self.tree = GopulatTreeWidget()
        self.editor = GopulateEditorWidget()
        self.tree.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.accept = QtGui.QPushButton('accept')
        layout = QtGui.QVBoxLayout(self)
        midLayout = QtGui.QHBoxLayout()
        midLayout.addWidget(self.tree)
        midLayout.addWidget(self.editor)
        layout.addLayout(midLayout)
        layout.addWidget(self.accept)
        
        self.tree.setModel(model)
        self.tree.setHeaderHidden(True)
        self.tree.selectionModel().currentChanged.connect(self.editor.setElement)
