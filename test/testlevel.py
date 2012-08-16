# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
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

import functools

from omg.core import levels, tags
from omg.core.elements import Container, File, Element
from omg.core.nodes import Wrapper
from omg import filebackends


class TestLevel(levels.Level):
    """A level for fake elements used in tests. Provides methods to easily add fake files and containers.""" 
    def __init__(self,name="TEST"):
        super().__init__(name,None) # no parent => no db access
        self.currentId = 0
        self.nameToElement = {}
        self.nameToId = {}
        
    def addContainer(self,name):
        """Add a container with the given name."""
        assert name not in self.nameToElement
        self.currentId -= 1
        container = Container(self,self.currentId,False)
        container.tags.add(tags.TITLE,name)
        self.elements[self.currentId] = container
        self.nameToElement[name] = container
        self.nameToId[name] = self.currentId
        return container
    
    def addFile(self,name):
        """Add a file with the given name."""
        assert name not in self.nameToElement
        self.currentId -= 1
        file = File(self,self.currentId,filebackends.BackendURL.fromString('file://test/'+name),100)
        file.tags.add(tags.TITLE,name)
        self.elements[self.currentId] = file
        self.nameToElement[name] = file
        self.nameToId[name] = self.currentId
        return file
        
    def addChild(self,parent,child):
        """Append *child* to the contents of *parent*."""
        if not isinstance(parent,Element):
            if isinstance(parent,str):
                parent = self.nameToElement[parent]
            else: parent = self.elements[parent]
        if not isinstance(child,Element):
            if isinstance(child,str):
                child = self.nameToElement[child]
            else: child = self.elements[child]
        if parent.id not in child.parents:
            child.parents.append(parent.id)
        parent.contents.append(child.id)
        
    def addAlbum(self,name,fileCount=5):
        """Add an album: Add a container of name *name* and *fileCount* files in the container Set the
        names of the files to *name* + number of the file."""
        container = self.addContainer(name)
        for i in range(1,fileCount+1):
            file = self.addFile(name+str(i))
            self.addChild(container,file)
        return container

    def ids(self,names):
        """Given a comma-separated list of element names, return a list of their ids."""
        return [self.nameToId[name] for name in names.split(',')]
        
    def makeWrappers(self,wrapperString,*wrapperNames):
        """Create a wrapper tree containing elements of this level and return its root node.
        *s* must be a string like   "X[A[A1,A2],B[B1,B2]],Z"
        where the identifiers must be names of existing elements of this level. This method does not check
        whether the given structure is valid.
        
        Often it is necessary to have references to some of the wrappers in the tree. For this reason
        this method accepts names of wrappers as optional arguments. It will then return a tuple consisting
        of the usual result (as above) and the wrappers with the given names (do not use this if there is
        more than one wrapper with the same name).
        """  
        wrappersToReturn = [None]*len(wrapperNames)
        createFunc = functools.partial(self._createFunc,wrapperNames,wrappersToReturn)
        roots = self.createWrappers(wrapperString,createFunc)
        
        if len(wrapperNames) == 0:
            return roots
        else:
            wrappersToReturn.insert(0,roots)
            return wrappersToReturn
        
    def _createFunc(self,wrapperNames,wrappersToReturn,parent,token):
        wrapper = Wrapper(self.nameToElement[token])
        if parent is not None:
            assert parent.element.id in wrapper.element.parents
            wrapper.parent = parent
        if token in wrapperNames:
            wrappersToReturn[wrapperNames.index(token)] = wrapper
        return wrapper
    
        
def getWrapperString(node):
    """Return a string that would - if submitted to TestLevel.makeWrappers - create the tree structure below
    *node*.""" 
    strFunc = lambda n: n.element.tags[tags.TITLE][0]
    return node.wrapperString(strFunc=strFunc)
