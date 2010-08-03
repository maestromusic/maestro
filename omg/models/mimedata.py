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

from omg import config, models

class MimeData(QtCore.QMimeData):
    """Subclass of QMimeData specialized to transport list of elements."""
    def __init__(self,model,indexList):
        QtCore.QMimeData.__init__(self)
        
        #TODO: Filter the index list for elements whose parents are contained, too (don't drag them twice)
        nodes = [model.data(index) for index in indexList]
        
        from . import browser
        if isinstance(model,browser.BrowserModel):
            # Add either the node or invoke getElements recursively
            self.elementList = itertools.chain(*[[node] if isinstance(node,models.Element)
                                                 else node.getElements() for node in nodes])
        else: self.elementList = nodes
        
    def hasFormat(self,format):
        return format == config.get("gui","mime")
    
    def formats(self):
        return [config.get("gui","mime")]
        
    def retrieveData(self,mimeType,type=None):
        if mimeType == config.get("gui","mime"):
            return self.elementList
        else:
            # return a null variant of the given type (confer the documentation of retrieveData)
            return QtCore.QVariant(type) if type is not None else QtCore.QVariant()