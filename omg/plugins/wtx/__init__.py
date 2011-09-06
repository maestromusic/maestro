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
    """Provides an action for the treeview's context menu (confer treeview.contextMenuProvider). The action
    will only be enabled if exactly one container is selected and in this case a save dialog for the XML file
    is opened.
    """
    action = QtGui.QAction(translate("WTX","Write to XML..."),treeview)
    elements = [element for element in treeview.getSelectedNodes() if element.isContainer()]
    if len(elements) == 0:
        action.setEnabled(False)
    else: action.triggered.connect(lambda: save(elements))
    actions.append(action)


def save(containers):
    # Ask the user for a path
    files = itertools.chain.from_iterable(container.getAllFiles() for container in containers)
    commonPath = strutils.commonPrefix(file.path for file in files)
    path = os.path.join(options.main.collection,commonPath)
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
    containerNode.setAttribute("major",'1' if container.major else '0')
    tags = document.createElement("tags")
    containerNode.appendChild(tags)
    if len(container.flags) > 0:
        flags = document.createElement("flags")
        containerNode.appendChild(flags)
    contents = document.createElement("contents")
    containerNode.appendChild(contents)

    for tag,values in container.tags.items():
        for value in values:
            node = document.createElement("tag")
            node.setAttribute("tag",tag.name)
            node.setAttribute("value",str(value))
            tags.appendChild(node)

    for flag in container.flags:
        node = document.createElement("flag")
        node.setAttribute("name",flag.name)
        flags.appendChild(node)
            
    for element in container.getContents():
        if element.isContainer():
            contents.appendChild(createContainerNode(document,element))
        else:
            fileNode = document.createElement("file")
            fileNode.setAttribute("pos",str(element.position))
            fileNode.setAttribute("path",str(element.path))
            contents.appendChild(fileNode)
            
            # Store flags
            if len(element.flags) > 0:
                flagNode = document.createElement("flags")
                fileNode.appendChild(flagNode)
                for flag in element.flags:
                    node = document.createElement("flag")
                    node.setAttribute("name",flag.name)
                    flagNode.appendChild(node)
            
            # And private tags
            if any(tag.private for tag in element.tags):
                tagNode = document.createElement("tags")
                fileNode.appendChild(tagNode)
                for tag in element.tags:
                    if tag.private:
                        node = document.createElement("tag")
                        node.setAttribute("tag",tag.name)
                        node.setAttribute("value",str(value))
                        tagNode.appendChild(node)

    return containerNode
