# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

import sys, os, re, logging
from functools import reduce
from difflib import SequenceMatcher

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

import omg.models
from omg import config, realfiles, relPath, absPath, tags, constants, database

import omg.database.queries as queries
from omg.models import rootedtreemodel


db = omg.database.get()
logger = logging.getLogger('gopulate')

FIND_DISC_RE=r" ?[([]?(?:cd|disc|part|teil|disk|vol)\.? ?([iI0-9]+)[)\]]?"

def finalize(album, metaContainer = False):
    if album.isFile():
        return
    album.contents.sort(key=lambda x : x.getPosition())
    album.updateSameTags(metaContainer)
    if not metaContainer:
        album.tags[tags.TITLE] = album.contents[0].tags[tags.ALBUM]

def findAlbumsInDirectory(path, onlyNewFiles = True):
    if not path:
        return []
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
        if tags.ALBUM in t:
            album = t[tags.ALBUM][0]
            if "discnumber" in t:
                album += "####••••{}".format(t["discnumber"][0])
            if not album in albumsInThisDirectory:
                albumsInThisDirectory[album] = omg.models.Container(id = None)
            elem.parent = albumsInThisDirectory[album]
            albumsInThisDirectory[album].contents.append(elem)
            if "tracknumber" in t:
                trkn = int(t["tracknumber"][0].split("/")[0]) # support 02/15 style
                elem.setPosition(trkn)
            else:
                elem.setPosition(0)
        elif tags.TITLE in t:
            album = t[tags.TITLE][0]
            albumsInThisDirectory[album] = elem
        else:
            album = filename
            albumsInThisDirectory[album] = elem
        
    
    for album in albumsInThisDirectory.values():
        finalize(album)
    
    finalDictionary = {}
    for name, album in albumsInThisDirectory.items():
        discnumber = None
        crazySplit = name.split("####••••")
        if len(crazySplit) == 2:
            discnumber = int(crazySplit[1].split("/")[0])
        discstring = re.findall(FIND_DISC_RE,album.tags[tags.ALBUM][0],flags=re.IGNORECASE)
        if len(discstring) > 0 and discnumber==None:
            discnumber = discstring[0]
            if discnumber.lower().startswith("i"): #roman number, support I-III :)
                discnumber = len(discnumber)
        if discnumber!= None:
            album.tags["discnumber"] = [ discnumber ]
            logger.info("detected part of a multi-disc container '{}'".format(album.tags[tags.TITLE][0]))
            discname_reduced = re.sub(FIND_DISC_RE,"",album.tags[tags.TITLE][0],flags=re.IGNORECASE)
            if discname_reduced in finalDictionary:
                metaContainer = finalDictionary[discname_reduced]
            else:
                discname_id = tags.TITLE.getValueId(discname_reduced, insert = False)
                if discname_id is not None:
                    album_id = database.get().query('SELECT element_id FROM tags WHERE tag_id=? and value_id= ?',
                                                    tags.TITLE.id, discname_id).getSingle()
                else:
                    album_id = None
                metaContainer = omg.models.Container(id = album_id)
                if metaContainer.isInDB():
                    print("existing found {}".format(metaContainer))
                finalDictionary[discname_reduced] = metaContainer
                
                metaContainer.loadContents(recursive=True)
                metaContainer.loadTags(recursive=True)
                print(metaContainer.tags)
                if not metaContainer.isInDB():
                    metaContainer.tags[tags.TITLE] = [discname_reduced]
                    metaContainer.tags[tags.ALBUM] = [discname_reduced]
            metaContainer.contents.append(album)
            album.setParent(metaContainer)
            album.setPosition(int(discnumber))
        else:
            finalDictionary[name] = album
    
    for album in set(finalDictionary.values()) - set(albumsInThisDirectory.values()):
        finalize(album, True)
        
    return finalDictionary.values()
        
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
    return reduce(longestSubstring,
                   ( ind.internalPointer().tags.getFormatted(tags.TITLE) for ind in indices )
                 ).strip(constants.FILL_CHARACTERS)
    