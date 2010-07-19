#!/usr/bin/env python3
'''
Created on 06.07.2010

@author: Michael Helmling
'''

import sys, os
from PyQt4 import QtCore, QtGui
import omg.models
from . import gui
from omg import config, realfiles
import logging
import omg.database.queries as queries
from omg.models import rootedtreemodel

logger = logging.getLogger('gopulate')

def relPath(file):
    """Returns the relative path of a music file against the collection base path."""
    return os.path.relpath(file,config.get("music","collection"))

def absPath(file):
    """Returns the absolute path of a music file inside the collection directory, if it is not absolute already."""
    if not os.path.isabs(file):
        return os.path.join(config.get("music","collection"),file)
    else:
        return file
    
class DirectoryNode(omg.models.Node):
    def __init__(self, path=None, parent=None):
        self.contents = []
        self.parent = parent
        self.path = path
    
    def __str__(self):
        return self.path

class GopulateAlbum(omg.models.Node):
    def __init__(self, name = None, parent=None):
        self.parent = parent
        self.contents = []
        self.tracks = {}
        self.name = name
        
    def __str__(self):
        return self.name
    
    def finalize(self):
        self.contents = []
        for i in sorted(self.tracks.keys()):
            self.contents.append(self.tracks[i])
            
        
class FileSystemFile(omg.models.Element):
    def __init__(self, path, tags = None, length = None, parent = None):
        self.path = path
        self.tags = tags
        self.length = length
        self.parent = parent
        
    def readTagsFromFilesystem(self):
        real = realfiles.File(absPath(self.path))
        real.read()
        self.tags = real.tags
        self.length = real.length
    
    def writeTagsToFilesystem(self):
        real = realfiles.File(absPath(self.path))
        real.tags = self.tags
        real.save_tags()
        
    def __str__(self):
        return str(self.tags)

class GopulateTreeModel(rootedtreemodel.RootedTreeModel):
    
    def __init__(self, dirs):
        rootedtreemodel.RootedTreeModel.__init__(self)
        self.dirs = dirs
        self.finder = None
        
    def nextDirectory(self):
        logger.debug('next directory, dirs: {}'.format(self.dirs))
        if not self.finder:
            if len(self.dirs) == 0:
                raise StopIteration()
            self.finder = findNewAlbums(self.dirs[0])
            del self.dirs[0]
        try:
            self._createTree(*next(self.finder))
        except StopIteration:
            self.finder = None
            self.nextDirectory()
    
    def _createTree(self, path, albums):
        root = DirectoryNode(path)
        for el in albums.values():
            print('element: {}'.format(el))
            root.contents.append(el)
            el.parent = root
        self.setRoot(root)
        
def findNewAlbums(path):
    """Generator function which tries to find albums in the filesystem tree.
    
    Yields an omg.Container without any tags. The tags and the name for the album should be examined by another function."""
    for dirpath, dirnames, filenames in os.walk(path):
        albumsInThisDirectory = {}
        ignored_albums=[]
        for filename in (os.path.normpath(os.path.abspath(os.path.join(dirpath, f))) for f in filenames):
            if queries.idFromFilename(relPath(filename)):
                logger.debug("Skipping file '{0}' which is already in the database.".format(filename))
                continue
            try:
                realfile = realfiles.File(os.path.abspath(filename))
                realfile.read()
            except realfiles.NoTagError:
                logger.warning("Skipping file '{0}' which has no tag".format(filename))
                continue
            t = realfile.tags
            if "album" in t:
                album = t["album"][0]
                if album in ignored_albums:
                    continue
                if not album in albumsInThisDirectory:
                    albumsInThisDirectory[album] = GopulateAlbum(album)
                file = FileSystemFile(filename, tags=t, length=realfile.length, parent=albumsInThisDirectory[album])
                if "tracknumber" in t:
                    trkn = int(t["tracknumber"][0].split("/")[0]) # support 02/15 style
                    albumsInThisDirectory[album].tracks[trkn] = file
                else: # file without tracknumber, bah
                    if 0 in albumsInThisDirectory[album].tracks:
                        print("More than one file in this album without tracknumber, don't know what to do: \n{0}".format(filename))
                        del albumsInThisDirectory[album]
                        ignored_albums.append(album)
                    else:
                        albumsInThisDirectory[album].tracks[0] = file
            else:
                print("Here is a file without album, I'll skip this: {0}".format(filename))
        if len(albumsInThisDirectory) == 0:
            continue
        for name,album in albumsInThisDirectory.items():
            logger.debug("I found an album '{0}' in directory '{1}' containing {2} files.".format(name,dirpath,len(album.contents)))
            album.finalize()
        yield dirpath,albumsInThisDirectory


def run(popdirs):
    # Switch first to the directory containing this file
    if os.path.dirname(__file__):
        os.chdir(os.path.dirname(__file__))
    # And then one directory above
    os.chdir("../")
    
    # Some Qt-classes need a running QApplication before they can be created
    app = QtGui.QApplication(sys.argv)

    # Import and initialize modules
    from omg import database
    database.connect()
    from omg import tags
    tags.updateIndexedTags()

    from omg.models.playlist import ExternalFile, RootNode
    from omg.models import Node, Element
    root = RootNode()
    teste = ExternalFile("Modern/ABBA/1999 - The Complete Singles Collection [Disc 1]/01 - People Need Love.ogg", root)
    testf = ExternalFile("/wtf/omg", root)
    root.contents.append(teste)
    root.contents.append(testf)
    n = DirectoryNode(root)
    testg = ExternalFile("aaa", n)
    testh = ExternalFile("bbb", n)
    n.contents.append(testg)
    n.contents.append(testh)
    root.contents.append(n)
    testm = rootedtreemodel.RootedTreeModel()
    testm.setRoot(root)
    
    gm = GopulateTreeModel(popdirs)
    
    # Create GUI
    window = QtGui.QWidget()
    layout = QtGui.QVBoxLayout(window)
    widget = gui.GopulateWidget(gm)
    layout.addWidget(widget)
    
    next = QtGui.QPushButton('next')
    layout.addWidget(next)
    
    next.clicked.connect(gm.nextDirectory)
    
    window.resize(800, 600)
    screen = QtGui.QDesktopWidget().screenGeometry()
    size =  window.geometry()
    window.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    run()
