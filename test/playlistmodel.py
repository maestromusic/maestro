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

"""Unittests for the sql-package."""

import sys, unittest, os.path
sys.path.insert(0,os.path.normpath(os.path.join(os.getcwd(),os.path.dirname(__file__),'../')))

from omg import application, config, database as db, utils
from omg.core import levels, tags
from omg.core.elements import File, Container, Element
from omg.core.nodes import Wrapper

from omg.models import playlist


class TestLevel(levels.Level):
    def __init__(self,name="TEST"):
        super().__init__(name,None) # no parent => no db access
        self.currentId = 0
        self.nameToElement = {}
        
    def addContainer(self,name):
        assert name not in self.nameToElement
        self.currentId -= 1
        container = Container(self,self.currentId,False)
        container.tags.add(tags.TITLE,name)
        self.elements[self.currentId] = container
        self.nameToElement[name] = container
        return container
    
    def addFile(self,name):
        assert name not in self.nameToElement
        self.currentId -= 1
        file = File(self,self.currentId,'test/'+name,100)
        file.tags.add(tags.TITLE,name)
        self.elements[self.currentId] = file
        self.nameToElement[name] = file
        return file
        
    def addChild(self,parent,child):
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
        container = self.addContainer(name)
        for i in range(1,fileCount+1):
            file = self.addFile(name+str(i))
            self.addChild(container,file)
        return container
    
    def createWrappers(self,s):
        roots = []
        currentWrapper = None
        currentList = roots
        for token in getTokens(s):
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
                currentList.append(wrapper)
                if currentWrapper is not None:
                    assert currentWrapper.element.id in wrapper.element.parents
                    wrapper.parent = currentWrapper
        return roots
    

def getTokens(s):
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
    parts = []
    for child in node.contents:
        if child.isFile() or child.getContentsCount() == 0:
            parts.append(child.element.tags[tags.TITLE][0])
        else:
            parts.append(child.element.tags[tags.TITLE][0]+'['+getWrapperString(child)+']')
    return ','.join(parts)
    
    
class PseudoBackend:
    def __init__(self):
        self.playlist = []
        
    def setPlaylist(self,paths):
        self.playlist = list(paths)
    
    def insertIntoPlaylist(self,pos,paths):
        self.playlist[pos:pos] = paths
    
    def removeFromPlaylist(self,begin,end):
        del self.playlist[begin:end+1]
    
    
class InsertTestCase(unittest.TestCase):
    def __init__(self,level,playlist):
        super().__init__()
        self.level = level
        self.playlist = playlist
    
    def runTest(self):
        level = self.level
        playlist = self.playlist
        
        # Insert some wrappers with no useful container structure
        playlist.insert(playlist.root,0,level.createWrappers('D1,E1,D1'))
        self.check('D1,E1,D1')
        
        # Check clear
        playlist.clear()
        self.check('')

        # Insert a container
        playlist.insert(playlist.root,0,level.createWrappers('A[A1,A2,A3]'))
        self.check('A[A1,A2,A3]')
        playlist.clear()
                
        # Insert part of an album. Also check that single parents are not added
        playlist.insert(playlist.root,0,level.createWrappers('A1,A2,A3'))
        self.check('A[A1,A2,A3]')
        playlist.clear()

        # Now the playlist has the longest sequence. Do not create any of A,C,X,Y,Z,T
        playlist.insert(playlist.root,0,level.createWrappers('A3,A2,A1,E3,D5,D4,D3'))
        self.check('A3,Pl[A2,A1,E3,D5,D4],D3')
        playlist.clear()
        
        # Insert into a node
        A = level.createWrappers('A')[0]
        playlist.insert(playlist.root,0,[A])
        playlist.insert(A,0,level.createWrappers('A1'))
        self.check('A[A1]')
        playlist.insert(A,1,level.createWrappers('A2'))
        self.check('A[A1,A2]')
        playlist.clear()
        
        # Create appropriate parents when inserting into a node
        X = level.createWrappers('X')[0]
        playlist.insert(playlist.root,0,[X])
        playlist.insert(X,0,level.createWrappers('A1'))
        self.check('X[A[A1]]')
        playlist.clear()
        
        # Split checks
        #=========================
        A = level.createWrappers('A[A1,A2]')[0]
        playlist.insert(playlist.root,0,[A])
        print("===================================f")
        playlist.insert(A,1,level.createWrappers('B'))
        self.check('A[A1],B,A[A2]')
        playlist.clear()
        
        # Split over several levels
        toplevel = level.createWrappers('T[X[A[A1,A2]]]')[0]
        playlist.insert(playlist.root,0,[toplevel])
        self.check('T[X[A[A1,A2]]]')
        A = toplevel.contents[0].contents[0]
        playlist.insert(A,1,level.createWrappers('E1'))
        self.check('T[X[A[A1]]],E1,T[X[A[A2]]]')
        playlist.clear()
        
        # Split some levels and create an appropriate parent 
        toplevel = level.createWrappers('T[X[A[A1,A2]]]')[0]
        playlist.insert(playlist.root,0,[toplevel])
        A = toplevel.contents[0].contents[0]
        playlist.insert(A,1,level.createWrappers('D1'))
        self.check('T[X[A[A1]],Y[D[D1]],X[A[A2]]]')
        playlist.clear()
                
        # Glue checks
        #=====================
        
        # Check simple glueing
        playlist.insert(playlist.root,0,level.createWrappers('A2,A3'))
        self.check('A[A2,A3]')
        playlist.insert(playlist.root,1,level.createWrappers('A4,A5'))
        self.check('A[A2,A3,A4,A5]')
        # Don't create parent containers here
        playlist.insert(playlist.root,1,level.createWrappers('B1,B2'))
        self.check('A[A2,A3,A4,A5],B[B1,B2]')
        playlist.clear()
                
        # Glue over several levels
        playlist.insert(playlist.root,0,level.createWrappers('T[X[A[A1,A2]]]'))
        playlist.insert(playlist.root,1,level.createWrappers('A3,A4'))
        self.check('T[X[A[A1,A2,A3,A4]]]')
        playlist.clear()      
        
        # Complicated glue (both ends, several levels)
        toplevel = level.createWrappers('T[X[A[A1]],Y[D[D2]]]')[0]
        playlist.insert(playlist.root,0,[toplevel])
        playlist.insert(toplevel,1,level.createWrappers('B1,C1,D1'))
        self.check('T[X[A[A1],B[B1],C[C1]],Y[D[D1,D2]]]')
        playlist.clear()
        
        # Glue and split together
        toplevel = level.createWrappers('T[X[A[A1],B[B1]]')[0]
        X = toplevel.contents[0]
        playlist.insert(playlist.root,0,[toplevel])
        playlist.insert(X,1,level.createWrappers('A2,E1,B2'))
        self.check('T[X[A[A1,A2]]],E1,T[X[B[B2,B1]]]')
        playlist.clear()
        
    def check(self,wrapperString):
        # Check tree structure
        self.assertEqual(wrapperString,getWrapperString(self.playlist.root))
        
        # Check flat playlist
        self.assertEqual(self.playlist.backend.playlist,
                         [f.element.path for f in self.playlist.root.getAllFiles()])
        




if __name__ == "__main__":
    application.init(exitPoint='noplugins')

    level = TestLevel()
    level.addAlbum('A')
    level.addAlbum('B')
    level.addAlbum('C')
    level.addAlbum('D')
    level.addAlbum('E')
    level.addContainer('X')
    level.addContainer('Y')
    level.addContainer('Z')
    level.addContainer('T')
    level.addChild('T','X')
    level.addChild('T','Y')
    level.addChild('X','A')
    level.addChild('X','B')
    level.addChild('X','C')
    level.addChild('Y','C')
    level.addChild('Y','D')
    level.addContainer('Pl')
    level.addChild('Pl','A1')
    level.addChild('Pl','A2')
    level.addChild('Pl','E3')
    level.addChild('Pl','D4')
    level.addChild('Pl','D5')
    
    print({id: element.tags[tags.TITLE][0] for id,element in level.elements.items()})
    
    playlist = playlist.PlaylistModel(backend=PseudoBackend(),level=level)
    
    suite = unittest.TestSuite()
    suite.addTest(InsertTestCase(level,playlist))
    unittest.TextTestRunner(verbosity=2).run(suite)
    
    
    
