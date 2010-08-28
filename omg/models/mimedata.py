#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
import itertools

from PyQt4 import QtCore
from PyQt4.QtCore import Qt

from omg import config, models, absPath

class MimeData(QtCore.QMimeData):
    """Subclass of QMimeData specialized to transport a tree of elements. It supports two MimeTypes: The first one is used internally by omg and stores the tree-structure. Its name is stored in the config variable "gui->mime". The second one is "text/uri-list" and contains a list of URLs to all files in the tree. This type is used by applications like Amarok and Dolphin."""
    def __init__(self,elementList):
        QtCore.QMimeData.__init__(self)
        self.elementList = elementList
        
    def hasFormat(self,format):
        return format in self.formats()
    
    def formats(self):
        return [config.get("gui","mime"),"text/uri-list"]
    
    def hasUrls(self):
        return True
        
    def retrieveData(self,mimeType,type=None):
        if mimeType == config.get("gui","mime"):
            return self.elementList
        elif mimeType == "text/uri-list":
            return self.urls()
        else:
            # return a null variant of the given type (confer the documentation of retrieveData)
            return QtCore.QVariant(type) if type is not None else QtCore.QVariant()

    def paths(self):
        """Return a list of absolute paths to all files contained in this MimeData-instance."""
        files = itertools.chain.from_iterable(element.getAllFiles() for element in self.elementList)
        return [absPath(file.getPath()) for file in files]
        
    def urls(self):
        return [QtCore.QUrl("file://"+path) for path in self.paths()]


def createFromIndexes(model,indexList):
    """Create a MimeData-instance containing the elements represented by the given indexes in <model>."""
    #TODO: Filter the index list for elements whose parents are contained, too (don't drag them twice)
    nodes = [model.data(index) for index in indexList]
    
    from . import browser
    if isinstance(model,browser.BrowserModel):
        # Add either the node or invoke getElements recursively
        return MimeData(itertools.chain.from_iterable(
                        [node] if isinstance(node,models.Element) else node.getElements() for node in nodes))
    else: return MimeData(nodes)