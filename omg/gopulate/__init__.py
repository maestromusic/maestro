# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

import sys, os
from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt
import omg.models
from omg import config, realfiles
import logging
import omg.database.queries as queries
import omg.database
from omg.models import rootedtreemodel
from functools import reduce

db = omg.database.get()
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

def findAlbumsInDirectory(path, onlyNewFiles = True):
    print("findAlbumsInDirectory called on {}".format(path))
    from omg.gopulate.models import GopulateContainer, FileSystemFile
    ignored_albums=[]
    newAlbumsInThisDirectory = {}
    existingAlbumsInThisDirectory = {}
    thingsInThisDirectory = []
    filenames = filter(os.path.isfile, (os.path.join(path,x) for x in os.listdir(path)))
    for filename in (os.path.normpath(os.path.abspath(os.path.join(path, f))) for f in filenames):
        id = queries.idFromFilename(relPath(filename))
        if id:
            print("file {} has id {}".format(filename, id))
            if onlyNewFiles:
                logger.debug("Skipping file '{0}' which is already in the database.".format(filename))
                continue
            else:
                elem = omg.models.Element(id)
                elem.loadTags()
                t = elem.tags
                albumIds = elem.getAlbumIds()
                print("albumIds: {}".format(albumIds))
                for aid in albumIds:
                    print("file is in album id {}".format(aid))
                    if not aid in existingAlbumsInThisDirectory:
                        existingAlbumsInThisDirectory[aid] = omg.models.Element(aid)
                        existingAlbumsInThisDirectory[aid].contents = []
                    existingAlbumsInThisDirectory[aid].contents.append(elem)
                    elem.parent = existingAlbumsInThisDirectory[aid]
                if len(albumIds) > 0:
                    continue
        else:
            try:
                realfile = realfiles.File(os.path.abspath(filename))
                realfile.read()
            except realfiles.NoTagError:
                logger.warning("Skipping file '{0}' which has no tag".format(filename))
                continue
            t = realfile.tags
            elem = FileSystemFile(filename, tags=t, length=realfile.length)
        if "album" in t:
            album = t["album"][0]
            if album in ignored_albums:
                continue
            if not album in newAlbumsInThisDirectory:
                newAlbumsInThisDirectory[album] = GopulateContainer(album)
            elem.parent = newAlbumsInThisDirectory[album]
            if "tracknumber" in t:
                trkn = int(t["tracknumber"][0].split("/")[0]) # support 02/15 style
                newAlbumsInThisDirectory[album].tracks[trkn] = elem
            else: # file without tracknumber, bah
                if 0 in newAlbumsInThisDirectory[album].tracks:
                    print("More than one file in this album without tracknumber, don't know what to do: \n{0}".format(filename))
                    del newAlbumsInThisDirectory[album]
                    ignored_albums.append(album)
                else:
                    newAlbumsInThisDirectory[album].tracks[0] = elem
        else:
            print("Here is a file without album, I'll skip this: {0}".format(filename))
    for t in existingAlbumsInThisDirectory.values():
        thingsInThisDirectory.append(t)
    for al in newAlbumsInThisDirectory.values():
        al.finalize()
        thingsInThisDirectory.append(al)
        print("album of length:{}".format(len(al.contents)))
    return thingsInThisDirectory
        
def findNewAlbums(path):
    """Generator function which tries to find albums in the filesystem tree.
    
    Yields an omg.Container without any tags. The tags and the name for the album should be examined by another function."""
    
    for dirpath, dirnames, filenames in os.walk(path):
        albumsInThisDirectory = findAlbumsInDirectory(dirpath, True)
        
        if len(albumsInThisDirectory) == 0:
            continue
        for album in albumsInThisDirectory:
            logger.debug("I found an album '{0}' in directory '{1}' containing {2} files.".format(
                      ", ".join(album.tags["album"]),dirpath,len(album.contents)))
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
#    dirm = QtGui.QFileSystemModel()
#    musikindex = dirm.setRootPath(config.get("music","collection"))
#    omg = QtGui.QTreeView()
#    omg.setModel(dirm)
#    omg.setRootIndex(musikindex)
#    omg.setWindowTitle("wtf?")
#    global dirmodel, gopmodel
#    dirmodel = dirm
#    gopmodel = gm
#    omg.selectionModel().currentChanged.connect(test)
    import omg.filebrowser
    fb = omg.filebrowser.FileSystemBrowser()
    fb.currentDirectoryChanged.connect(gm.setSearchDirectories)
    mdi.addSubWindow(structWidget).resize(800,800)
    mdi.addSubWindow(fb).resize(600,800)
    testw = QtGui.QLabel()
    testw.setText("<b>hallo?</b>hallo!<img src=\"images/lastfm.gif\"></img>")
    mdi.addSubWindow(testw)
    mdi.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    run()
