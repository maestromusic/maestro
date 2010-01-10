#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

# Temporary tables used for search results (have to appear before the imports as they will be imported in some imports)
TT_BIG_RESULT = 'tmp_browser_bigres'
TT_SMALL_RESULT = 'tmp_browser_smallres'

from PyQt4 import QtGui
from omg import search, database, tags
from . import delegate, layouter

class Browser(QtGui.QWidget):
    def __init__(self,model,parent=None):
        QtGui.QWidget.__init__(self, parent)
        
        search.createResultTempTable(TT_BIG_RESULT,True)
        search.createResultTempTable(TT_SMALL_RESULT,True)
        
        self.valueNodeTags = [tags.ARTIST,tags.COMPOSER]
        
        # Browser
        self.browser = QtGui.QTreeView(self)
        self.browser.setHeaderHidden(True)
        self.browser.setModel(model)
        self.browser.setItemDelegate(delegate.Delegate(self,model,layouter.ComplexLayouter()))
        self.browser.expandsOnDoubleClick = False
        
        # OptionMenu
        optionMenu = QtGui.QMenu(self)
        optionMenu.addAction(QtGui.QAction("Bla und Blubb",self))
        
        # ControlLine
        self.searchBox = QtGui.QLineEdit(self)
        self.searchBox.returnPressed.connect(self.search)
        self.optionButton = QtGui.QToolButton(self)
        self.optionButton.setIcon(QtGui.QIcon("images/icons/options.png"))
        self.optionButton.setPopupMode(QtGui.QToolButton.InstantPopup)
        self.optionButton.setMenu(optionMenu)
        
        # Layout
        layout = QtGui.QVBoxLayout(self)
        controlLineLayout = QtGui.QHBoxLayout()
        layout.addLayout(controlLineLayout)
        layout.addWidget(self.browser)
        self.setLayout(layout)
        controlLineLayout.addWidget(QtGui.QLabel("Suche:",self))
        controlLineLayout.addWidget(self.searchBox)
        controlLineLayout.addWidget(self.optionButton)

    def search(self):
        db = database.get()
        
        search.textSearch(self.searchBox.text(),TT_BIG_RESULT)
        
        # Create value nodes
        valueNodes = []
        
        for tag in self.valueNodeTags:
            result = db.query("""
                SELECT DISTINCT tag_{0}.id,tag_{0}.value
                FROM {1} JOIN tags ON {1}.id = tags.container_id AND tags.tag_id = {2}
                         JOIN tag_{0} ON tags.value_id = tag_{0}.id
                """.format(tag.name,TT_BIG_RESULT,tag.id))
            for row in result:
                valueNodes.append(models.ValueNode(row[1],search.matchclasses.TagIdMatch({tag:row[0]})))
        
        for node in valueNodes:
            node.load()
        
        #~ for node in valueNodes:
            #~ print(node)
        
        self.browser.model().setRoots(valueNodes)
        self.browser.expandAll()