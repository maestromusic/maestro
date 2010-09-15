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
from difflib import SequenceMatcher

db = omg.database.get()
logger = logging.getLogger('gopulate')

def finalize(album):
    if album.isFile():
        return
    album.contents.sort(key=lambda x : x.getPosition())
    album.updateSameTags()
    album.tags['title'] = album.contents[0].tags['album']

def findAlbumsInDirectory(path, onlyNewFiles = True):
    ignored_albums=[]
    albumsInThisDirectory = {} # name->container map
    existingAlbumsInThisDirectory = {} #id->container map
    filenames = filter(os.path.isfile, (os.path.join(path,x) for x in os.listdir(path)))
    for filename in (os.path.normpath(os.path.abspath(os.path.join(path, f))) for f in filenames):
        id = queries.idFromFilename(relPath(filename))
        if id:
            if onlyNewFiles:
                logger.debug("Skipping file '{0}' which is already in the database.".format(filename))
                continue
            else:
                elem = omg.models.File(id)
                elem.loadTags()
                t = elem.tags
                albumIds = elem.getAlbumIds()
                for aid in albumIds:
                    if not aid in existingAlbumsInThisDirectory:
                        existingAlbumsInThisDirectory[aid] = omg.models.Container(aid)
                        existingAlbumsInThisDirectory[aid].loadTags()
                    exAlb = existingAlbumsInThisDirectory[aid]
                    exAlbName = exAlb.tags.getFormatted(tags.get('title'))
                    if not exAlbName in albumsInThisDirectory:
                        albumsInThisDirectory[exAlbName] = exAlb
                    
                    elem.parent = exAlb
                    elem.getPosition()
                    elem.parent = albumsInThisDirectory[exAlbName]
                    albumsInThisDirectory[exAlbName].contents.append(elem)
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
            elem = omg.models.File(id = None, path = filename, tags=t, length=realfile.length)
        if "album" in t:
            album = t["album"][0]
            if not album in albumsInThisDirectory:
                albumsInThisDirectory[album] = omg.models.Container(id = None)
            elem.parent = albumsInThisDirectory[album]
            albumsInThisDirectory[album].contents.append(elem)
            if "tracknumber" in t:
                trkn = int(t["tracknumber"][0].split("/")[0]) # support 02/15 style
                elem.position=trkn
            else:
                elem.position=0
        elif "title" in t:
            album = t["title"][0]
            albumsInThisDirectory[album] = elem
        else:
            album = filename
            albumsInThisDirectory[album] = elem
        
    
    for al in albumsInThisDirectory.values():
        finalize(al)
    return albumsInThisDirectory.values()
        
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

def longestSubstring(a, b):
    sm = SequenceMatcher(None, a, b)
    result = sm.find_longest_match(0, len(a), 0, len(b))
    return a[result[0]:result[0]+result[2]]
    
def calculateMergeHint(indices):
    return reduce(longestSubstring, ( ind.internalPointer().tags.getFormatted(tags.get("title")) for ind in indices )).strip(":- ")
    