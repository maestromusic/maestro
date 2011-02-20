#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

import os.path, itertools
from xml.dom import minidom

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

from omg import models, strutils
from omg.config import options
from omg.gui import treeview

translate = QtGui.QApplication.translate

def enable():
    treeview.contextMenuProviders['all'].append(contextMenuProvider)
    
def disable():
    treeview.contextMenuProviders['all'].remove(contextMenuProvider)

def contextMenuProvider(treeview,actions,currentIndex):
    """Provides an action for the treeview's context menu (confer treeview.contextMenuProvider). The action will only be enabled if exactly one container is selected and in this case a save dialog for the XML file is opened."""
    action = QtGui.QAction(translate("WTX","Write to XML..."),treeview)
    elements = [element for element in treeview.getSelectedNodes() if element.isContainer()]
    if len(elements) == 0:
        action.setEnabled(False)
    else: action.triggered.connect(lambda: save(elements))
    actions.append(action)

def save(containers):
    # Ask the user for a path
    files = itertools.chain.from_iterable(container.getAllFiles() for container in containers)
    commonPath = strutils.commonPrefix(file.getPath() for file in files)
    path = os.path.join(options.music.collection,commonPath)
    path = QtGui.QFileDialog.getSaveFileName(QtGui.QApplication.activeWindow(),translate("WTX","Save XML"),
                                             path,translate("WTX","XML files (*.xml)"))
    if path:
        # Create XML tree
        implementation = minidom.getDOMImplementation()
        document = implementation.createDocument(None,"structure",None)
        for container in containers:
            document.documentElement.appendChild(createContainerNode(document,container))

        # And save it
        file = open(path,'w')
        document.writexml(file, indent="", addindent="  ", newl="\n", encoding="utf-8")

def createContainerNode(document,container):
    containerNode = document.createElement("container")
    tags = document.createElement("tags")
    contents = document.createElement("contents")
    containerNode.appendChild(tags)
    containerNode.appendChild(contents)

    for tag,values in container.tags.items():
        for value in values:
            node = document.createElement("tag")
            node.setAttribute("tag",tag.name)
            node.setAttribute("value",str(value))
            tags.appendChild(node)

    for element in container.getChildren():
        if element.isContainer():
            contents.appendChild(createContainerNode(document,element))
        else:
            file = document.createElement("file")
            file.setAttribute("pos",str(element.getPosition()))
            file.setAttribute("path",str(element.getPath()))
            contents.appendChild(file)

    return containerNode
