# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import itertools

from PyQt4 import QtCore
from PyQt4.QtCore import Qt

from ..utils import absPath
from .. import config, models


class MimeData(QtCore.QMimeData):
    """Subclass of QMimeData specialized to transport a tree of elements. It supports two MimeTypes: The first
    one is used internally by omg and stores the tree-structure. Its name is stored in the config variable 
    "gui->mime". The second one is "text/uri-list" and contains a list of URLs to all files in the tree. This
    type is used by applications like Amarok and Dolphin."""
    def __init__(self,nodeList):
        QtCore.QMimeData.__init__(self)
        self.nodeList = nodeList
        
    def hasFormat(self,format):
        return format in self.formats()
    
    def formats(self):
        return [config.options.gui.mime,"text/uri-list"]
    
    def hasUrls(self):
        return True
        
    def retrieveData(self,mimeType,type=None):
        if mimeType == config.options.gui.mime:
            return self.elementList
        elif mimeType == "text/uri-list":
            return self.urls()
        else:
            # return a null variant of the given type (confer the documentation of retrieveData)
            return QtCore.QVariant(type) if type is not None else QtCore.QVariant()

    def getNodes(self):
        """Return the list of elements stored in this MimeData instance."""
        return self.nodeList
    
    def getFiles(self):
        """Return all files contained in the elements stored in this MimeData instance."""
        return itertools.chain.from_iterable(node.getAllFiles() for node in self.getNodes())
        
    def paths(self):
        """Return a list of absolute paths to all files contained in this MimeData-instance."""
        return [absPath(file.path) for file in self.getFiles()]
        
    def urls(self):
        return [QtCore.QUrl("file://"+path) for path in self.paths()]

    @staticmethod
    def fromIndexes(model,indexList):
        """Generate a MimeData instance from the indexes in *indexList*. *model* must be the model containing
        these indexes. This method will remove an index when an ancestor is contained in *indexList*, too.
        """
        nodes = [model.data(index,role=Qt.EditRole) for index in indexList]
        # Filter away nodes if a parent is also contained in the indexList. 
        nodes = [n for n in nodes if not any(parent in nodes for parent in n.getParents())]
        return MimeData(nodes)
