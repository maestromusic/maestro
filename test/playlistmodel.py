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

"""Unittests for the PlaylistModel."""

import sys, unittest, os.path
sys.path.insert(0,os.path.normpath(os.path.join(os.getcwd(),os.path.dirname(__file__),'../')))

from omg import application, config, database as db, utils
from omg.models import playlist
from testlevel import *


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
    

class PlaylistTestCase(unittest.TestCase):
    """Base test case for playlist test cases."""
    def __init__(self,level,playlist):
        super().__init__()
        self.level = level
        self.playlist = playlist
        self.checks = []
        self.lastStackIndex = 0
        
    def check(self,wrapperString,redo=True):
        """Check whether the current tree structure as well as the flat playlist is in agreement with
        *wrapperString* (a string in the format for TestLevel.getWrappers).
        
        If *redo* is True, record the test so that it can be performed again when checkUndo is called.
        """
        # Check tree structure
        self.assertEqual(wrapperString,getWrapperString(self.playlist.root))
        
        # Check flat playlist
        self.assertEqual(self.playlist.backend.playlist,
                         [f.element.path for f in self.playlist.root.getAllFiles()])
        
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
        
        wrappers,A = level.createWrappers('A[A1,A2]','A')
        playlist.insert(playlist.root,0,wrappers)
        playlist.insert(A,1,level.createWrappers('B'))
        self.check('A[A1],B,A[A2]')
        playlist.clear()
        
        # Split over several levels
        wrappers,toplevel,A = level.createWrappers('T[X[A[A1,A2]]]','T','A')
        playlist.insert(playlist.root,0,wrappers)
        self.check('T[X[A[A1,A2]]]')
        playlist.insert(A,1,level.createWrappers('E1'))
        self.check('T[X[A[A1]]],E1,T[X[A[A2]]]')
        playlist.clear()
        
        # Split some levels and create an appropriate parent 
        wrappers,toplevel,A = level.createWrappers('T[X[A[A1,A2]]]','T','A')
        playlist.insert(playlist.root,0,wrappers)
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
        
        # Check glueing with a container that is not below the insertion parent
        wrappers,A = level.createWrappers('A[A1],E[E2]','A')
        playlist.insert(playlist.root,0,wrappers)
        playlist.insert(A,1,level.createWrappers('A2,E1'))
        self.check('A[A1,A2],E[E1,E2]')
        playlist.clear()
        
        # Glue over several levels
        playlist.insert(playlist.root,0,level.createWrappers('T[X[A[A1,A2]]]'))
        playlist.insert(playlist.root,1,level.createWrappers('A3,A4'))
        self.check('T[X[A[A1,A2,A3,A4]]]')
        playlist.clear()      
        
        # Complicated glue (both ends, several levels)
        wrappers,toplevel = level.createWrappers('T[X[A[A1]],Y[D[D2]]]','T')
        playlist.insert(playlist.root,0,wrappers)
        playlist.insert(toplevel,1,level.createWrappers('B1,C1,D1'))
        self.check('T[X[A[A1],B[B1],C[C1]],Y[D[D1,D2]]]')
        playlist.clear()
        
        # Glue and split together
        wrappers,X = level.createWrappers('T[X[A[A1],B[B1]]','X')
        playlist.insert(playlist.root,0,wrappers)
        playlist.insert(X,1,level.createWrappers('A2,E1,B2'))
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
        playlist.insert(playlist.root,0,level.createWrappers('A1,E2,A3'))
        playlist.remove(playlist.root,1,1)
        self.check('A1,A3')
        playlist.clear()
        
        # From a parent
        wrappers,A = level.createWrappers('A[A1,A2,A3]','A')
        playlist.insert(playlist.root,0,wrappers)
        playlist.remove(A,1,1)
        self.check('A[A1,A3]')
        playlist.clear()
        
        # Recursive
        playlist.insert(playlist.root,0,level.createWrappers('A[A1,A2],E1'))
        playlist.remove(playlist.root,0,0)
        self.check('E1')
        playlist.clear()
        
        # Remove several ranges below the same parent
        wrappers,A = level.createWrappers('A[A1,A2,A3,A4,A5,A1,A2,A3]','A')
        playlist.insert(playlist.root,0,wrappers)
        playlist.removeMany([(A,1,3),(A,5,6)])
        self.check('A[A1,A5,A3]')
        playlist.clear()
        
        # Remove empty parent
        wrappers,A = level.createWrappers('A[A1,A2],E1','A')
        playlist.insert(playlist.root,0,wrappers)
        playlist.remove(A,0,1)
        self.check('E1')
        playlist.clear()
        
        # Remove several empty parents (making another parent empty)
        wrappers,A,B = level.createWrappers('T[X[A[A1,A2],B[B1,B2]],Y[D[D1]]','A','B')
        playlist.insert(playlist.root,0,wrappers)
        playlist.removeMany([(A,0,1),(B,0,1)])
        self.check('T[Y[D[D1]]]')
        playlist.clear()
        
        # Glue
        playlist.insert(playlist.root,0,level.createWrappers('A[A1,A2],E1,A[A3,A4]'))
        playlist.remove(playlist.root,1,1)
        self.check('A[A1,A2,A3,A4]')
        playlist.clear()
        
        # Glue several levels
        wrappers,X = level.createWrappers('X[A[A1,A2],B[B1],A[A3,A4]]','X')
        playlist.insert(playlist.root,0,wrappers)
        playlist.remove(X,1,1)
        self.check('X[A[A1,A2,A3,A4]]')
        playlist.clear()
        
        # Glue several levels after removing empty parents (this changes the glue position)
        wrappers,B,C = level.createWrappers('X[A[A1,A2],B[B1],C[C1],A[A3,A4]]','B','C')
        playlist.insert(playlist.root,0,wrappers)
        playlist.removeMany([(B,0,0),(C,0,0)])
        self.check('X[A[A1,A2,A3,A4]]')
        playlist.clear()
        
        self.checkUndo()
        
        
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
    
    #print({id: element.tags[tags.TITLE][0] for id,element in level.elements.items()})
    
    playlist = playlist.PlaylistModel(backend=PseudoBackend(),level=level)
    
    suite = unittest.TestSuite()
    suite.addTest(InsertTestCase(level,playlist))
    suite.addTest(RemoveTestCase(level,playlist))
    unittest.TextTestRunner(verbosity=2).run(suite)
    