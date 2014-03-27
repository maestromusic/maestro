# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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

"""Unittests for the PlaylistModel."""

import unittest

from omg import application, config, database as db, utils
from omg.models import playlist as playlistmodel

from .testlevel import *


class PseudoBackend:
    """Pseudo backend that simply manages a flat list of files.""" 
    def __init__(self):
        self.playlist = []
        
    def setPlaylist(self,paths):
        self.playlist = list(paths)
    
    def insertIntoPlaylist(self,pos,paths):
        self.playlist[pos:pos] = paths
    
    def removeFromPlaylist(self,begin,end):
        del self.playlist[begin:end]
    
    def move(self,fromOffset,toOffset):
        if fromOffset != toOffset:
            file = self.playlist.pop(fromOffset)
            self.playlist.insert(toOffset,file)


class PlaylistTestCase(unittest.TestCase):
    """Base test case for playlist test cases."""
    def __init__(self,level,playlist=None):
        super().__init__()
        self.level = level
        self.playlist = playlist
        self.checks = []
        
    def check(self,wrapperString,redo=True):
        """Check whether the current tree structure as well as the flat playlist is in agreement with
        *wrapperString* (a string in the format for TestLevel.getWrappers).
        
        If *redo* is True, record the test so that it can be performed again when checkUndo is called.
        """
        # Check tree structure
        self.assertEqual(wrapperString,getWrapperString(self.playlist.root))
        
        # Check flat playlist
        self.assertEqual(self.playlist.backend.playlist,
                         [f.element.url for f in self.playlist.root.getAllFiles()])
        
        if redo:
            self.checks.append((wrapperString,application.stack.index()))
        
    def checkUndo(self):
        """Undo all changes to the playlist and do the checks again at the right moments."""
        for wrapperString,index in reversed(self.checks):
            application.stack.setIndex(index)
            self.check(wrapperString,redo=False)
        
        application.stack.setIndex(0)
        self.check('',redo=False) # all steps undone
        
        
class InsertTestCase(PlaylistTestCase):
    """Test case for the insert algorithm, including treebuilder, split and glue."""
    def runTest(self):
        level = self.level
        playlist = self.playlist
        
        # Insert a single wrapper. Do not add a parent
        playlist.insert(playlist.root,0,level.makeWrappers('A1'))
        self.check('A1')
        
        # Check clear
        playlist.clear()
        self.check('')
        
        # Insert some wrappers with no useful container structure
        playlist.insert(playlist.root,0,level.makeWrappers('D1,E1,D1'))
        self.check('D1,E1,D1')
        playlist.clear()

        # Insert a container
        playlist.insert(playlist.root,0,level.makeWrappers('A[A1,A2,A3]'))
        self.check('A[A1,A2,A3]')
        playlist.clear()
                
        # Insert part of an album. Also check that single parents are not added
        playlist.insert(playlist.root,0,level.makeWrappers('A1,A2,A3'))
        self.check('A[A1,A2,A3]')
        playlist.clear()
        
        # Insert the same file twice (ticket #131)
        playlist.insert(playlist.root,0,level.makeWrappers('A1,A1'))
        self.check('Pl[A1,A1]')
        playlist.clear()
        
        # Now the playlist has the longest sequence. Do not create any of A,C,X,Y,Z,T
        playlist.insert(playlist.root,0,level.makeWrappers('A3,A2,A1,E3,D5,D4,D3'))
        self.check('A3,Pl[A2,A1,E3,D5,D4],D3')
        playlist.clear()
        
        # Insert into a node
        A = level.makeWrappers('A')[0]
        playlist.insert(playlist.root,0,[A])
        playlist.insert(A,0,level.makeWrappers('A1'))
        self.check('A[A1]')
        playlist.insert(A,1,level.makeWrappers('A2'))
        self.check('A[A1,A2]')
        playlist.clear()
        
        # Create appropriate parents when inserting into a node
        X = level.makeWrappers('X')[0]
        playlist.insert(playlist.root,0,[X])
        playlist.insert(X,0,level.makeWrappers('A1'))
        self.check('X[A[A1]]')
        playlist.clear()
        
        # Split checks
        #=========================
        
        wrappers,A = level.makeWrappers('A[A1,A2]','A')
        playlist.insert(playlist.root,0,wrappers)
        playlist.insert(A,1,level.makeWrappers('B'))
        self.check('A[A1],B,A[A2]')
        playlist.clear()
        
        # Split over several levels
        wrappers,toplevel,A = level.makeWrappers('T[X[A[A1,A2]]]','T','A')
        playlist.insert(playlist.root,0,wrappers)
        self.check('T[X[A[A1,A2]]]')
        playlist.insert(A,1,level.makeWrappers('E1'))
        self.check('T[X[A[A1]]],E1,T[X[A[A2]]]')
        playlist.clear()
        
        # Split some levels and create an appropriate parent 
        wrappers,toplevel,A = level.makeWrappers('T[X[A[A1,A2]]]','T','A')
        playlist.insert(playlist.root,0,wrappers)
        playlist.insert(A,1,level.makeWrappers('D1'))
        self.check('T[X[A[A1]],Y[D[D1]],X[A[A2]]]')
        playlist.clear()
                
        # Glue checks
        #=====================
        # Check simple glueing
        playlist.insert(playlist.root,0,level.makeWrappers('A2,A3'))
        self.check('A[A2,A3]')
        playlist.insert(playlist.root,1,level.makeWrappers('A4,A5'))
        self.check('A[A2,A3,A4,A5]')
        # Don't create parent containers here
        playlist.insert(playlist.root,1,level.makeWrappers('B1,B2'))
        self.check('A[A2,A3,A4,A5],B[B1,B2]')
        playlist.clear()
        
        # Check glueing with a container that is not below the insertion parent
        wrappers,A = level.makeWrappers('A[A1],E[E2]','A')
        playlist.insert(playlist.root,0,wrappers)
        playlist.insert(A,1,level.makeWrappers('A2,E1'))
        self.check('A[A1,A2],E[E1,E2]')
        playlist.clear()
        
        # Glue over several levels
        playlist.insert(playlist.root,0,level.makeWrappers('T[X[A[A1,A2]]]'))
        playlist.insert(playlist.root,1,level.makeWrappers('A3,A4'))
        self.check('T[X[A[A1,A2,A3,A4]]]')
        playlist.clear()      
        
        # Complicated glue (both ends, several levels)
        wrappers,toplevel = level.makeWrappers('T[X[A[A1]],Y[D[D2]]]','T')
        playlist.insert(playlist.root,0,wrappers)
        playlist.insert(toplevel,1,level.makeWrappers('B1,C1,D1'))
        self.check('T[X[A[A1],B[B1],C[C1]],Y[D[D1,D2]]]')
        playlist.clear()
        
        # Glue and split together
        wrappers,X = level.makeWrappers('T[X[A[A1],B[B1]]','X')
        playlist.insert(playlist.root,0,wrappers)
        playlist.insert(X,1,level.makeWrappers('A2,E1,B2'))
        self.check('T[X[A[A1,A2]]],E1,T[X[B[B2,B1]]]')
        playlist.clear()
        
        self.checkUndo()
        
        
class RemoveTestCase(PlaylistTestCase):
    def setUp(self):
        self.playlist.clear()
        application.stack.clear()
        
    def runTest(self):
        level = self.level
        playlist = self.playlist
        
        # Simple remove
        playlist.insert(playlist.root,0,level.makeWrappers('A1,E2,A3'))
        playlist.remove(playlist.root,1,1)
        self.check('A1,A3')
        playlist.clear()
        
        # From a parent
        wrappers,A = level.makeWrappers('A[A1,A2,A3]','A')
        playlist.insert(playlist.root,0,wrappers)
        playlist.remove(A,1,1)
        self.check('A[A1,A3]')
        playlist.clear()
        
        # Recursive
        playlist.insert(playlist.root,0,level.makeWrappers('A[A1,A2],E1'))
        playlist.remove(playlist.root,0,0)
        self.check('E1')
        playlist.clear()
        
        # Remove parent and node below
        wrappers,A = level.makeWrappers('A[A1,A2],E1','A')
        playlist.insert(playlist.root,0,wrappers)
        playlist.removeMany([(playlist.root,0,0),(A,0,0)])
        self.check('E1')
        playlist.clear()
        
        # Remove several ranges below the same parent
        wrappers,A = level.makeWrappers('A[A1,A2,A3,A4,A5,A1,A2,A3]','A')
        playlist.insert(playlist.root,0,wrappers)
        playlist.removeMany([(A,1,3),(A,5,6)])
        self.check('A[A1,A5,A3]')
        playlist.clear()
        
        # Remove empty parent
        wrappers,A = level.makeWrappers('A[A1,A2],E1','A')
        playlist.insert(playlist.root,0,wrappers)
        playlist.remove(A,0,1)
        self.check('E1')
        playlist.clear()
        
        # Remove several empty parents (making another parent empty)
        wrappers,A,B = level.makeWrappers('T[X[A[A1,A2],B[B1,B2]],Y[D[D1]]','A','B')
        playlist.insert(playlist.root,0,wrappers)
        playlist.removeMany([(A,0,1),(B,0,1)])
        self.check('T[Y[D[D1]]]')
        playlist.clear()
        
        # Glue
        playlist.insert(playlist.root,0,level.makeWrappers('A[A1,A2],E1,A[A3,A4]'))
        playlist.remove(playlist.root,1,1)
        self.check('A[A1,A2,A3,A4]')
        playlist.clear()
        
        # Glue several levels
        wrappers,X = level.makeWrappers('X[A[A1,A2],B[B1],A[A3,A4]]','X')
        playlist.insert(playlist.root,0,wrappers)
        playlist.remove(X,1,1)
        self.check('X[A[A1,A2,A3,A4]]')
        playlist.clear()
        
        # Glue several levels after removing empty parents (this changes the glue position)
        wrappers,B,C = level.makeWrappers('X[A[A1,A2],B[B1],C[C1],A[A3,A4]]','B','C')
        playlist.insert(playlist.root,0,wrappers)
        playlist.removeMany([(B,0,0),(C,0,0)])
        self.check('X[A[A1,A2,A3,A4]]')
        playlist.clear()
        
        # Several glues below the same parent (indexes might get wrong)
        wrappers,B1,B3 = level.makeWrappers('X[A[A1],B[B1],A[A2],B[B2],A[A3],B[B3],A[A4]]','B1','B3')
        playlist.insert(playlist.root,0,wrappers)
        playlist.removeMany([(B1.parent,0,0),(B3.parent,0,0)])
        self.check('X[A[A1,A2],B[B2],A[A3,A4]]')
        playlist.clear()
        
        self.checkUndo()
        

class MoveTestCase(PlaylistTestCase):
    def setUp(self):
        self.playlist.clear()
        application.stack.clear()
        
    def runTest(self):
        level = self.level
        playlist = self.playlist
        
        # Simply swap some elements
        wrappers,A = level.makeWrappers('A[A1,A2,A3]','A')
        playlist.insert(playlist.root,0,wrappers)
        playlist.move([A.contents[1]],A,3)
        self.check('A[A1,A3,A2]')
        playlist.clear()
        
        # Other direction
        wrappers,A = level.makeWrappers('A[A1,A2,A3]','A')
        playlist.insert(playlist.root,0,wrappers)
        playlist.move([A.contents[2]],A,1)
        self.check('A[A1,A3,A2]')
        playlist.clear()
        
        # Move several elements
        wrappers,A = level.makeWrappers('A[A1,A2,A3,A4,A5]','A')
        playlist.insert(playlist.root,0,wrappers)
        playlist.move([A.contents[0],A.contents[2],A.contents[3]],A,5)
        self.check('A[A2,A5,A1,A3,A4]')
        playlist.clear()
        
        # Move recursively
        wrappers,X,A = level.makeWrappers('X[A[A1,A2,A3],B[B1,B2],C[C1]]','X','A')
        playlist.insert(playlist.root,0,wrappers)
        playlist.move([A],X,2)
        self.check('X[B[B1,B2],A[A1,A2,A3],C[C1]]')
        playlist.clear()
        
        # Move in between
        wrappers,A = level.makeWrappers('A[A1,A2,A3,A4,A5]','A')
        playlist.insert(playlist.root,0,wrappers)
        playlist.move([A.contents[0],A.contents[3],A.contents[4]],A,3)
        self.check('A[A2,A3,A1,A4,A5]')
        playlist.clear()
        
        # Move into child (must not work)
        wrappers,X,B,Y = level.makeWrappers('X[A[A1,A2,A3],B[B1,B2]],Y[D[D1]]','X','B','Y')
        playlist.insert(playlist.root,0,wrappers)
        oldStackPos = application.stack.index()
        self.assertFalse(playlist.move([X,Y],B,0))
        self.assertEqual(oldStackPos,application.stack.index())
        playlist.clear()
        
        # Move with glue, split and remove empty parents
        wrappers,A,A5,B1,B2 = level.makeWrappers('X[A[A1,A2,A3,A4,A5],B[B1,B2]]','A','A5','B1','B2')
        playlist.insert(playlist.root,0,wrappers)
        playlist.move([A5,B1,B2],A,2)
        self.check('X[A[A1,A2,A5],B[B1,B2],A[A3,A4]]')
        playlist.clear()
        
        # Remove wrappers in a way that decreases the insert position by glueing and removing empty parents
        wrappers,E1,E2,E3 = level.makeWrappers('A[A1,A2],E1,A[A3,A4],E[E2,E3],A[A5]','E1','E2','E3')
        playlist.insert(playlist.root,0,wrappers)
        playlist.move([E1,E2,E3],playlist.root,5) # Real insert position will be 1!
        self.check('A[A1,A2,A3,A4,A5],E[E1,E2,E3]')
        playlist.clear()
        
        # Horrible move: After removing the nodes, the move target might be glued away
        wrappers,X,B1 = level.makeWrappers('X[A[A1,A2],B[B1],A[A3,A4,A5]]','X','B1')
        playlist.insert(playlist.root,0,wrappers)
        playlist.move([B1],X.contents[2],3)
        self.check('X[A[A1,A2,A3,A4,A5],B[B1]]')
        playlist.clear()
        
        # Horrible move in the other direction
        wrappers,X,B1 = level.makeWrappers('X[A[A1,A2],B[B1],A[A3,A4,A5]]','X','B1')
        playlist.insert(playlist.root,0,wrappers)
        playlist.move([B1],X.contents[0],0)
        self.check('X[B[B1],A[A1,A2,A3,A4,A5]]')
        playlist.clear()
        
        self.checkUndo()
    

def load_tests(loader, standard_tests, pattern):
    # See http://docs.python.org/py3k/library/unittest.html#load-tests-protocol
    suite = unittest.TestSuite()
        
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

    print(["{}: {}".format(id,level.elements[id].tags[tags.TITLE][0]) for id in sorted(level.elements.keys())])
    
    playlist = playlistmodel.PlaylistModel(backend=PseudoBackend(),level=level)
    
    suite.addTest(InsertTestCase(level,playlist))
    suite.addTest(RemoveTestCase(level,playlist))
    suite.addTest(MoveTestCase(level,playlist))
    
    return suite
    
if __name__ == "__main__":
    print("To run this test use: python setup.py test --test-suite=test.playlistmodel")
    