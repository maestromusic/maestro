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
from omg import config, realfiles, relPath, absPath, tags
import logging
import omg.database.queries as queries
import omg.database
from omg.models import rootedtreemodel
from functools import reduce

db = omg.database.get()
logger = logging.getLogger('gopulate')


def findAlbumsInDirectory(path, onlyNewFiles = True):
    from omg.gopulate.models import GopulateContainer, FileSystemFile
    ignored_albums=[]
    newAlbumsInThisDirectory = {}
    existingAlbumsInThisDirectory = {}
    thingsInThisDirectory = []
    filenames = filter(os.path.isfile, (os.path.join(path,x) for x in os.listdir(path)))
    for filename in (os.path.normpath(os.path.abspath(os.path.join(path, f))) for f in filenames):
        id = queries.idFromFilename(relPath(filename))
        if id:
            if onlyNewFiles:
                logger.debug("Skipping file '{0}' which is already in the database.".format(filename))
                continue
            else:
                elem = omg.models.DBFile(id)
                elem.loadTags()
                t = elem.tags
                albumIds = elem.getAlbumIds()
                for aid in albumIds:
                    if not aid in existingAlbumsInThisDirectory:
                        existingAlbumsInThisDirectory[aid] = omg.models.Container(aid)
                        existingAlbumsInThisDirectory[aid].contents = []
                        existingAlbumsInThisDirectory[aid].loadTags()
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
                elem.position=trkn
            else: # file without tracknumber, bah
                print(t)
                if 0 in newAlbumsInThisDirectory[album].tracks:
                    logger.warning("More than one file in this album without tracknumber, don't know what to do: \n{0}".format(filename))
                    del newAlbumsInThisDirectory[album]
                    ignored_albums.append(album)
                else:
                    newAlbumsInThisDirectory[album].tracks[0] = elem
        else:
            logger.warning("Here is a file without album, I'll skip this: {0}".format(filename))
    for t in existingAlbumsInThisDirectory.values():
        if tags.get("title") in t.tags and t.tags["title"][0] in newAlbumsInThisDirectory:
            album = t.tags['title'][0]
            newAlbumsInThisDirectory[album].mergeWithExisting(t)
        else:
            t.contents.sort(key=lambda x : x.getPosition())
            thingsInThisDirectory.append(t)
    for al in newAlbumsInThisDirectory.values():
        al.finalize()
        thingsInThisDirectory.append(al)
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
