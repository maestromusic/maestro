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

from omg.core import levels, tags
from omg.core.elements import Container, File, Element
from omg.core.nodes import Wrapper


class TestLevel(levels.Level):
    """A level for fake elements used in tests. Provides methods to easily add fake files and containers.""" 
    def __init__(self,name="TEST"):
        super().__init__(name,None) # no parent => no db access
        self.currentId = 0
        self.nameToElement = {}
        
    def addContainer(self,name):
        """Add a container with the given name."""
        assert name not in self.nameToElement
        self.currentId -= 1
        container = Container(self,self.currentId,False)
        container.tags.add(tags.TITLE,name)
        self.elements[self.currentId] = container
        self.nameToElement[name] = container
        return container
    
    def addFile(self,name):
        """Add a file with the given name."""
        assert name not in self.nameToElement
        self.currentId -= 1
        file = File(self,self.currentId,'test/'+name,100)
        file.tags.add(tags.TITLE,name)
        self.elements[self.currentId] = file
        self.nameToElement[name] = file
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
    
    def createWrappers(self,s,*wrapperNames):
        """Create a wrapper tree containing elements of this level and return its root node.
        *s* must be a string like   "X[A[A1,A2],B[B1,B2]],Z"
        where the identifiers must be names of existing elements of this level. This method does not check
        whether the given structure is valid.
        
        Often it is necessary to have references to some of the wrappers in the tree. For this reason
        this method accepts names of wrappers as optional arguments. It will then return a tuple consisting
        of the usual result (as above) and the wrappers with the given names (do not use this if there is
        more than one wrapper with the same name).
        """  
        roots = []
        currentWrapper = None
        currentList = roots
        # Will be appended to the result
        wrappersToReturn = [None]*len(wrapperNames)
        for token in _getTokens(s):
            #print("Token: {}".format(token))
            if token == ',':
                continue
            if token == '[':
                currentWrapper = currentList[-1]
                currentList = currentWrapper.contents
            elif token == ']':
                currentWrapper = currentWrapper.parent
                if currentWrapper is None:
                    currentList = roots
                else: currentList = currentWrapper.contents
            else:
                wrapper = Wrapper(self.nameToElement[token])
                if token in wrapperNames:
                    wrappersToReturn[wrapperNames.index(token)] = wrapper
                currentList.append(wrapper)
                if currentWrapper is not None:
                    assert currentWrapper.element.id in wrapper.element.parents
                    wrapper.parent = currentWrapper
        
        if len(wrapperNames) == 0:
            return roots
        else:
            wrappersToReturn.insert(0,roots)
            return wrappersToReturn
    

def _getTokens(s):
    """Helper for TestLevel.getWrappers: Yield each token of *s*."""
    last = 0
    i = 0
    while i < len(s):
        if s[i] in (',','[',']'):
            if last != i:
                yield s[last:i]
            last = i+1
            yield s[i]
        i += 1
    if last != i:
        yield s[last:i]
    
        
def getWrapperString(node):
    """Return a string that would - if submitted to TestLevel.getWrappers - create the tree structure below
    *node*.""" 
    parts = []
    for child in node.contents:
        if child.isFile() or child.getContentsCount() == 0:
            parts.append(child.element.tags[tags.TITLE][0])
        else:
            parts.append(child.element.tags[tags.TITLE][0]+'['+getWrapperString(child)+']')
    return ','.join(parts)
    