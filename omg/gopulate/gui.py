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
import omg.gopulate

class GopulateDelegate(AbstractDelegate):
    def __init__(self,parent):
        AbstractDelegate.__init__(self,parent)
        
    def layout(self, index):
        elem = index.internalPointer()
        if (isinstance(elem,omg.gopulate.GopulateAlbum)):
            for k in elem.sameTags:
                for v in elem.tags[k]:
                    self.addLine("{}={}".format(k,v))
        elif (isinstance(elem,omg.gopulate.FileSystemFile)):
            for k,vs in elem.tags.items():
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
        
class GopulateWidget(QtGui.QWidget):
    
    def __init__(self, model=None):
        QtGui.QWidget.__init__(self)
        self.tree = QtGui.QTreeView()
        self.editor = GopulateEditorWidget()
        delegate = GopulateDelegate(self.tree)
        self.tree.setItemDelegate(delegate)
        self.tree.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.tree.setAlternatingRowColors(True)
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
