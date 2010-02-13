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
    DIRECTLOAD_LIMIT = 30
    
    def __init__(self,model,parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.model = model
        
        search.createResultTempTable(TT_BIG_RESULT,True)
        search.createResultTempTable(TT_SMALL_RESULT,True)
        
        self.valueNodeTags = [tags.ARTIST,tags.COMPOSER]
        
        # Browser
        self.browser = QtGui.QTreeView(self)
        self.browser.setHeaderHidden(True)
        self.browser.setModel(model)
        self.browser.setItemDelegate(delegate.Delegate(self,model,layouter.ComplexLayouter()))
        self.browser.setExpandsOnDoubleClick(False)
        self.browser.expanded.connect(self.onExpand)
        
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

    def onExpand(self,index):
        pass
        
    def search(self):
        db = database.get()
        search.textSearch(self.searchBox.text(),TT_BIG_RESULT)
        
        # Create value nodes
        valueNodes = []
        values = []
        for tag in self.valueNodeTags:
            # Get all values and corresponding ids of the given tag appearing in at least one direct result
            result = db.query("""
                SELECT DISTINCT tag_{0}.id,tag_{0}.value
                FROM {1} JOIN tags ON {1}.id = tags.container_id AND tags.tag_id = {2}
                         JOIN tag_{0} ON tags.value_id = tag_{0}.id
                """.format(tag.name,TT_BIG_RESULT,tag.id))
            for row in result:
                try:
                    # If there is already a value node with value row[1] add this tag to the query
                    valueNodes[values.index(row[1])].match.addMatches({tag,row[0]})
                except ValueError: # there is no value node of this value...so add one
                    valueNodes.append(models.ValueNode(row[1],search.matchclasses.TagIdMatch({tag:row[0]})))
        del values
        
        # Load value nodes if not more results than DIRECT_LOAD_LIMIT were found and merge nodes which have only one child
        if db.query("SELECT COUNT(*) FROM {0}".format(TT_BIG_RESULT)).getSingle() <= self.DIRECTLOAD_LIMIT:
            for i in range(0,len(valueNodes)):
                node = valueNodes[i]
                node.load()
                # If the node contains only one child, merge it into the child and replace it by the child
                if node.getElementsCount() == 1:
                    child = node.getElements()[0]
                    valueNodes[i] = child
                    child.mergeWithParent()
            # If valueNodeTags contains more than one tag after merging nodes the same node may appear twice (for example if valueNodeTags contains tags.ARTIST and tags.COMPOSER a piece may be found and merged twice. Therefore we eliminate the second appearance:
            seenIds = []
            pos = 0
            while pos < len(valueNodes):
                node = valueNodes[pos]
                if isinstance(node,models.ElementNode): # node has been merged
                    if node.id not in seenIds:
                        seenIds.append(node.id)
                        pos += 1
                    else: del valueNodes[pos]
                else: pos += 1
        
        self.model.setRoots(valueNodes)