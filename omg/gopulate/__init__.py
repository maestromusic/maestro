# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

import sys, os, re, logging, threading, queue
from functools import reduce
from difflib import SequenceMatcher

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

import omg.models
from omg import realfiles, relPath, absPath, tags, constants, database

import omg.database.queries as queries
from omg.models import rootedtreemodel
from omg.config import options


db = omg.database.get()
logger = logging.getLogger('gopulate')

FIND_DISC_RE=r" ?[([]?(?:cd|disc|part|teil|disk|vol)\.? ?([iI0-9]+)[)\]]?"

commitQueue = queue.Queue()
def commiter():
    """Run function for the commit thread."""
    while True:
        fun, args, kwargs = commitQueue.get()
        fun(*args, **kwargs)
        commitQueue.task_done()
        logger.debug("task done")
        
commitThread = threading.Thread(target = commiter)
commitThread.daemon = True
commitThread.start()


def terminate():
    """Terminates this module; waits for all threads to complete."""
    
    commitQueue.join() # wait until all tasks in the commit queue are done
    
    
class GopulateGuesser:
    """This class is used to 'guess' the correct container structure of files that are not yet contained in the database."""
    
    def __init__(self, files = None, directories = None):
        """initializes a GopulateGuesser with the given list of files, an iterable of absolute paths."""
        if files:
            self.files = files
        elif directories:
            self.findFiles(directories)
        else:
            self.files = None
    
    def _findFilesInDirectory(self, directory):
        filenames = filter(os.path.isfile, (os.path.join(directory,x) for x in os.listdir(directory)))
        return [os.path.normpath(os.path.abspath(os.path.join(directory, f))) for f in filenames]
    
    def findFiles(self, directories, recursive = False):
        """Look for files in the given directories. If recursive is True, also subdirectories are searched."""
        if not recursive:
            self.files = reduce(lambda a,b:a + b, (self._findFilesInDirectory(dir) for dir in directories))
        else:
            self.files = []
            for directory in directories:
                for dirpath, dirnames, filenames in os.walk(directory):
                    filenames = filter(os.path.isfile, (os.path.join(dirpath,x) for x in filenames))
                    self.files.extend((os.path.normpath(os.path.abspath(os.path.join(dirpath, f))) for f in filenames))
        
    def guessTree(self, onlyNewFiles = True):
        """Tries to guess the container tree of this Guesser's files. If the second argument is True, files in the DB will be ignored."""
        
        if self.files == None:
            return []
        albumsFoundByName = {} # name->container map
        albumsFoundByID = {} #id->container map
        
        for filename in self.files:
            id = queries.idFromFilename(relPath(filename))
            if id:
                if onlyNewFiles:
                    logger.debug("Skipping file '{0}' which is already in the database.".format(filename))
                    continue
                elem = omg.models.File(id)
                elem.loadTags()
                t = elem.tags
                albumIds = elem.getAlbumIds()
                for aid in albumIds:
                    if not aid in albumsFoundByID:
                        albumsFoundByID[aid] = omg.models.Container(aid)
                        albumsFoundByID[aid].loadTags()
                    exAlb = albumsFoundByID[aid]
                    exAlbName = exAlb.tags.getFormatted(tags.get('title'))
                    if not exAlbName in albumsFoundByName:
                        albumsFoundByName[exAlbName] = exAlb
                    
                    elem.parent = exAlb
                    elem.getPosition()
                    elem.parent = albumsFoundByName[exAlbName]
                    albumsFoundByName[exAlbName].contents.append(elem)
                if len(albumIds) > 0:
                    continue
            else:
                try:
                    realfile = realfiles.File(os.path.abspath(filename))
                    realfile.read()
                    t = realfile.tags
                    elem = omg.models.File(id = None, path = filename, tags=t, length=realfile.length)
                    del realfile
                except realfiles.NoTagError:
                    logger.warning("Skipping file '{0}' which has no tag".format(filename))
                    continue
            if tags.ALBUM in t:
                album = t[tags.ALBUM][0] # we don't support multiple album tags
                if "discnumber" in t:
                    album += "####••••{}".format(t["discnumber"][0])
                if not album in albumsFoundByName:
                    albumsFoundByName[album] = omg.models.Container(id = None)
                elem.parent = albumsFoundByName[album]
                albumsFoundByName[album].contents.append(elem)
                if "tracknumber" in t:
                    trkn = int(t["tracknumber"][0].split("/")[0]) # support 02/15 style
                    elem.setPosition(trkn)
                else:
                    elem.setPosition(0)
            elif tags.TITLE in t:
                album = t[tags.TITLE][0]
                albumsFoundByName[album] = elem
            else:
                album = filename
                albumsFoundByName[album] = elem
            
        
        for album in albumsFoundByName.values():
            finalize(album)
        
        finalDictionary = {}
        for name, album in albumsFoundByName.items():
            discnumber = None
            crazySplit = name.split("####••••")
            if len(crazySplit) == 2:
                discnumber = int(crazySplit[1].split("/")[0])
            if tags.ALBUM in album.tags:
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
                    finalDictionary[discname_reduced] = metaContainer
                    
                    metaContainer.loadContents(recursive=True)
                    metaContainer.loadTags(recursive=True)

                    if not metaContainer.isInDB():
                        metaContainer.tags[tags.TITLE] = [discname_reduced]
                        metaContainer.tags[tags.ALBUM] = [discname_reduced]
                alreadyThere = False
                for alb in metaContainer.contents:
                    if alb.isInDB() and album.isInDB() and alb.id == album.id:
                        alreadyThere = True
                if not alreadyThere:
                    metaContainer.contents.append(album)
                    album.setParent(metaContainer)
                    album.setPosition(int(discnumber))
            else:
                finalDictionary[name] = album
        
        for album in set(finalDictionary.values()) - set(albumsFoundByName.values()):
            finalize(album, True)
            
        return finalDictionary.values()
        
def finalize(album, metaContainer = False):
    if album.isFile():
        return
    album.contents.sort(key=lambda x : x.getPosition() or -1)
    album.updateSameTags(metaContainer)
    if not metaContainer:
        album.tags[tags.TITLE] = album.contents[0].tags[tags.ALBUM]


        
def findNewAlbums(path):
    """Generator function which tries to directory-wise find albums in the filesystem tree.
    
    Yields an omg.Container without any tags. The tags and the name for the album should be examined by another function."""
    for dirpath, dirnames, filenames in os.walk(path):
        guesser = GopulateGuesser(directories = [dirpath])
        albumsInThisDirectory = guesser.guessTree(True)
        
        if len(albumsInThisDirectory) == 0:
            continue
        for album in albumsInThisDirectory:
            logger.debug("I found an album '{0}' in directory '{1}' containing {2} files.".format(
                      ", ".join(album.tags["album"]),dirpath,len(album.contents)))
        yield albumsInThisDirectory

def longestSubstring(a, b):
    sm = SequenceMatcher(None, a, b)
    result = sm.find_longest_match(0, len(a), 0, len(b))
    return a[result[0]:result[0]+result[2]]
    
def calculateMergeHint(indices):
    return reduce(longestSubstring,
                   ( ind.internalPointer().tags.getFormatted(tags.TITLE) for ind in indices )
                 ).strip(constants.FILL_CHARACTERS)
    