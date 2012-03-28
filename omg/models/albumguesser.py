# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
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

from ..utils import relPath
from . import Container, levels
from .. import tags, modify
from ..modify import commands

from collections import OrderedDict
import os, re, itertools

from PyQt4 import QtCore 
translate = QtCore.QCoreApplication.translate

class GuessError(ValueError):
    pass
        
def guessAlbums(filesByFolder, albumGroupers, metacontainer_regex):
    """Try to guess the album structure of *filesByFolder*, using *albumGroupers* to group albums together.
    *albumGroupers* is a list of either tags or the string "DIRECTORY"; *filesByFolder* is a dict mapping
    directory to File instances contained therein."""
    if len(albumGroupers) == 0:
        # no grouping -> concatenate filesByFolder
        return list(itertools.chain(*filesByFolder.values()))
    else:
        modify.beginMacro('album guessing')
        if "DIRECTORY" in albumGroupers:
            albums = []
            singles = []
            for k,v in sorted(filesByFolder.items()):
                try:
                    al, si = guessAlbumsInDirectory(v, albumGroupers)
                    albums.extend(al)
                    singles.extend(si)
                except GuessError as e:
                    from ..gui.dialogs import warning
                    warning(translate(__name__, "Error guessing albums"), str(e))
                    singles.extend(v)
        else:
            try:
                albums, singles = guessAlbumsInDirectory(itertools.chain(*filesByFolder.values()), albumGroupers)
            except GuessError as e:
                from ..gui.dialogs import warning
                warning(translate(__name__, "Error guessing albums"), str(e))
                singles.extend(itertools.chain(*filesByFolder.values()))
        
        if albumGroupers == ["DIRECTORY"] or True:
            complete = albums + singles
        else:
            complete = guessMetaContainers(albums, albumGroupers, metacontainer_regex) + singles
        modify.endMacro()
        return complete

class AlbumGuessCommand(commands.ElementChangeCommand):
    
    contents = True
    
    def __init__(self, level, containerTags, children):
        super().__init__()
        self.level = level
        self.containerTags = containerTags
        self.containerID = None
        self.children = children
        self.ids = list(children.values())
    
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
    
    def undoChanges(self):
        del self.level.elements[self.containerID]
        for childID in self.children.values():
            self.level.get(childID).parents.remove(self.containerID)
        
def guessAlbumsInDirectory(files, albumGroupers):
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
            byExistingParent[element.level.get(element.parents[0])] = element
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
                children[element.tags.position] = element.id
            for i, element in enumerate(elementsWithoutPos, start = elementsWithPos[-1].tags.position+1 if len(elementsWithPos) > 0 else 1):
                children[i] = element.id
            albumTags = tags.findCommonTags(elements, False)
            albumTags[tags.TITLE] = [key] if dirMode else elements[0].tags[albumTag]
            command = AlbumGuessCommand(levels.editor, albumTags, children)
            modify.push(command)
            returnedAlbumIDs.append(command.containerID)
        else:
            returnedSingleIDs.extend(element.id for element in elements)
    return returnedAlbumIDs, returnedSingleIDs
                
                
    
def guessMetaContainers(albums, albumGroupers, meta_regex):
    # search for meta-containers in albums
    groupTags = albumGroupers[:]
    albumTag = groupTags[0]
    if "DIRECTORY" in groupTags:
        groupTags.remove("DIRECTORY")
    metaContainers = OrderedDict()
    result = []
    for album in albums:
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
            if (key, discname_reduced) in metaContainers:
                metaContainer = metaContainers[(key, discname_reduced)]
            else:
                metaContainer = Container(modify.newEditorId(), None, tags.Storage(), [], None, True)
                metaContainers[(key, discname_reduced)] = metaContainer
            metaContainer.contents.append(album)
            album.position = discnumber
            album.parent = metaContainer
            album.major = False
        else:
            result.append(album)
    for key, meta in metaContainers.items():
        meta.tags = tags.findCommonTags(meta.contents, True)
        meta.tags[tags.TITLE] = [key[1]]
        meta.tags[albumTag] = [key[1]]
        meta.sortContents()
        for i in range(1, len(meta.contents)):
            if meta.contents[i].position == meta.contents[i-1].position:
                raise RuntimeError('multiple positions below same meta-container -- please fix this with TagEditor!!')
        result.append(meta)
    return result