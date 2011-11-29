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
from . import Container
from .. import modify, tags

from collections import OrderedDict
import os, re

class GuessError(ValueError):
    pass
        
def guessAlbums(elements, albumGroupers):
        groupTags = albumGroupers[:]
        albumTag = groupTags[0]
        dirMode = albumTag == "DIRECTORY"
        if "DIRECTORY" in groupTags:
            groupTags.remove("DIRECTORY")
        byKey = {}
        for element in elements:
            if dirMode:
                key = relPath(os.path.dirname(element.path))
            else:
                key = tuple( (tuple(element.tags[tag]) if tag in element.tags else None) for tag in groupTags)
            if key not in byKey:
                byKey[key] = []
            byKey[key].append(element)
            if element.position is None:
                element.position = 1
        singles, albums = [], []
        for key, elements in byKey.items():
            if dirMode or (albumTag in elements[0].tags):
                album = Container(modify.newEditorId(), [], tags.Storage(), [], None, True)
                for elem in sorted(elements, key = lambda e: e.position):
                    if len(album.contents) > 0 and album.contents[-1].position == elem.position:
                        raise GuessError('multiple positions below album "{}" -- '
                            'please fix this with TagEditor!!'.format(key))
                    album.contents.append(elem)
                    elem.parent = album
                album.tags = tags.findCommonTags(album.contents, True)
                album.tags[tags.TITLE] = [key] if dirMode else elem.tags[albumTag]
                albums.append(album)
            else:
                for element in elements:
                    element.position = None
                singles.extend(elements)
        return albums, singles
    
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