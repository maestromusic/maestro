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


from . import Container, levels
from .. import tags, modify
from ..modify import commands
from ..utils import relPath

import os, re, itertools

from PyQt4 import QtCore 
translate = QtCore.QCoreApplication.translate

class GuessError(ValueError):
    pass
        
def guessAlbums(level, filesByFolder, albumGroupers, metacontainer_regex):
    """Try to guess the album structure of *filesByFolder*, using *albumGroupers* to group albums together.
    *albumGroupers* is a list of either tags or the string "DIRECTORY"; *filesByFolder* is a dict mapping
    directory to File instances contained therein."""
    if len(albumGroupers) == 0:
        # no grouping -> concatenate filesByFolder
        return [f.id for f in itertools.chain(*filesByFolder.values())]
    else:
        modify.beginMacro('album guessing')
        if "DIRECTORY" in albumGroupers:
            albums = []
            singles = []
            for k,v in sorted(filesByFolder.items()):
                try:
                    al, si = guessAlbumsInDirectory(level, v, albumGroupers)
                    albums.extend(al)
                    singles.extend(si)
                except GuessError as e:
                    from ..gui.dialogs import warning
                    warning(translate(__name__, "Error guessing albums"), str(e))
                    singles.extend([file.id for file in v])
        else:
            try:
                albums, singles = guessAlbumsInDirectory(level, itertools.chain(*filesByFolder.values()), albumGroupers)
            except GuessError as e:
                from ..gui.dialogs import warning
                warning(translate(__name__, "Error guessing albums"), str(e))
                singles.extend(f.id for f in itertools.chain(*filesByFolder.values()))
        
        if albumGroupers == ["DIRECTORY"]:
            complete = albums + singles
        else:
            try:
                complete = guessMetaContainers(level, albums, albumGroupers, metacontainer_regex) + singles
            except GuessError as e:
                from ..gui.dialogs import warning
                warning(translate(__name__, "Error guessing meta-containers"), str(e))
                complete = albums + singles    
        modify.endMacro()
        return complete

class AlbumGuessCommand(commands.ElementChangeCommand):
    
    contents = True
    
    def __init__(self, level, containerTags, children, meta = False):
        super().__init__()
        self.level = level
        self.containerTags = containerTags
        self.containerID = None
        self.children = children
        self.ids = list(children.values())
        self.meta = meta
    
    def redoChanges(self):
        if self.containerID is None:
            self.containerID = levels.createTId()
            self.ids.append(self.containerID)
        album = Container(self.level, self.containerID, major = True)
        album.tags = self.containerTags
        self.level.elements[self.containerID] = album
        for position, childID in self.children.items():
            child = self.level.get(childID)
            child.parents.append(self.containerID)
            album.contents[position] = childID
            if self.meta and child.isContainer():
                child.major = False
    
    def undoChanges(self):
        del self.level.elements[self.containerID]
        for childID in self.children.values():
            child = self.level.get(childID)
            child.parents.remove(self.containerID)
            if self.meta and child.isContainer():
                child.major = True
        
def guessAlbumsInDirectory(level, files, albumGroupers):
    groupTags = albumGroupers[:]
    albumTag = groupTags[0]
    dirMode = albumTag == "DIRECTORY"
    # "dirMode" means that all files in one directory are grouped to one album
    if "DIRECTORY" in groupTags:
        groupTags.remove("DIRECTORY")
    byKey = {}
    byExistingParent = {}
    returnedAlbumIDs = []
    returnedSingleIDs = []
    for element in files:
        if len(element.parents) > 0:
            byExistingParent[level.get(element.parents[0])] = element
        else:
            if dirMode:
                key = relPath(os.path.dirname(element.path))
            else:
                key = tuple( (tuple(element.tags[tag]) if tag in element.tags else None) for tag in groupTags)
            if key not in byKey:
                byKey[key] = []
            byKey[key].append(element)
    for key, elements in byKey.items():
        if dirMode or (albumTag in elements[0].tags):
            elementsWithoutPos = { e for e in elements if e.tags.position is None }
            elementsWithPos = sorted(set(elements) - elementsWithoutPos, key = lambda e: e.tags.position)
            children = {}
            for element in elementsWithPos:
                if element.tags.position in children:
                    raise GuessError("position {} appears twice in {}".format(element.tags.position, key))
                children[element.tags.position] = element.id
            for i, element in enumerate(elementsWithoutPos, start = elementsWithPos[-1].tags.position+1 if len(elementsWithPos) > 0 else 1):
                children[i] = element.id
            albumTags = tags.findCommonTags(elements)
            albumTags[tags.TITLE] = [key] if dirMode else elements[0].tags[albumTag]
            command = AlbumGuessCommand(level, albumTags, children)
            modify.push(command)
            returnedAlbumIDs.append(command.containerID)
        else:
            returnedSingleIDs.extend(element.id for element in elements)
    return returnedAlbumIDs, returnedSingleIDs
                
                
    
def guessMetaContainers(level, albumIDs, albumGroupers, meta_regex):
    # search for meta-containers in albums
    groupTags = albumGroupers[:]
    albumTag = groupTags[0]
    if "DIRECTORY" in groupTags:
        groupTags.remove("DIRECTORY")
    
    byKey = {}
    returnedTopIDs = []
    for albumID in albumIDs:
        album = level.get(albumID)
        name = ", ".join(album.tags[tags.TITLE])
        discstring = re.findall(meta_regex, name,flags=re.IGNORECASE)
        if len(discstring) > 0:
            discnumber = discstring[0]
            if discnumber.lower().startswith("i"): #roman number, support I-III :)
                discnumber = len(discnumber)
            else:
                discnumber = int(discnumber)
            discname_reduced = re.sub(meta_regex,"",name,flags=re.IGNORECASE)
            key = tuple( (tuple(album.tags[tag]) if tag in album.tags else None) for tag in groupTags[1:])
            if (key, discname_reduced) not in byKey:
                byKey[(key, discname_reduced)] = {}
            if discnumber in byKey[(key,discname_reduced)]:
                raise GuessError("disc-number {} appears twice in meta-container {}".format(discnumber, key))
            byKey[(key,discname_reduced)][discnumber] = album
        else:
            returnedTopIDs.append(albumID)
    for key, contents in byKey.items():
        metaTags = tags.findCommonTags(contents.values())
        metaTags[tags.TITLE] = [key[1]]
        metaTags[albumTag] = [key[1]]
        command = AlbumGuessCommand(level, metaTags, {pos:album.id for pos,album in contents.items()}, meta = True)
        modify.push(command)
        returnedTopIDs.append(command.containerID)
    return returnedTopIDs