#!/usr/bin/env python3
'''
Created on 06.07.2010

@author: Michael Helmling
'''

import sys, os
from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt
import omg.models
from omg import config, realfiles
import logging
import omg.database.queries as queries
from omg.models import rootedtreemodel
from functools import reduce


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

        
def findNewAlbums(path):
    """Generator function which tries to find albums in the filesystem tree.
    
    Yields an omg.Container without any tags. The tags and the name for the album should be examined by another function."""
    
    from omg.gopulate.models import GopulateContainer, FileSystemFile
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
                    albumsInThisDirectory[album] = GopulateContainer(album)
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

dirmodel = None
gopmodel = None
def test(current, previous):
    gopmodel.setSearchDirectories( [dirmodel.filePath(current)] )
    gopmodel.nextDirectory()

def run(popdirs):
    
    import omg.gopulate
    from omg.gopulate.models import DirectoryNode, GopulateTreeModel
    import omg.gopulate.gui
    
    # Some Qt-classes need a running QApplication before they can be created
    app = QtGui.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    # Import and initialize modules
    from omg import database
    database.connect()
    from omg import tags
    tags.updateIndexedTags()

    from omg.models.playlist import ExternalFile, RootNode
    from omg.models import Node, Element
    
    gm = GopulateTreeModel(popdirs)

    # Create GUI
    mdi = QtGui.QMdiArea()
    structWidget = QtGui.QWidget()
    layout = QtGui.QVBoxLayout(structWidget)
    widget = gui.GopulateWidget(gm)
    layout.addWidget(widget)
    
    next = QtGui.QPushButton('next')
    layout.addWidget(next)
    
    next.clicked.connect(gm.nextDirectory)
    
    mdi.resize(1400, 1000)
    screen = QtGui.QDesktopWidget().screenGeometry()
    size =  structWidget.geometry()
    mdi.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)
    dirm = QtGui.QFileSystemModel()
    musikindex = dirm.setRootPath("/ftp/musik")
    omg = QtGui.QTreeView()
    omg.setModel(dirm)
    omg.setRootIndex(musikindex)
    omg.setWindowTitle("wtf?")
    global dirmodel, gopmodel
    dirmodel = dirm
    gopmodel = gm
    omg.selectionModel().currentChanged.connect(test)
    mdi.addSubWindow(structWidget).resize(800,800)
    mdi.addSubWindow(omg).resize(600,800)
    testw = QtGui.QLabel()
    testw.setText("<b>hallo?</b>hallo!<img src=\"images/lastfm.gif\"></img>")
    mdi.addSubWindow(testw)
    mdi.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    run()
