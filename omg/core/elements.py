# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2013 Martin Altmayer, Michael Helmling
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

import os.path, bisect

from PyQt4 import QtCore
translate = QtCore.QCoreApplication.translate

from . import tags as tagsModule
from .. import config, filebackends, utils

ELEMENT_TYPES = range(4)
TYPE_NONE, TYPE_ALBUM, TYPE_WORK, TYPE_COLLECTION = ELEMENT_TYPES
MAJOR_TYPES = (TYPE_ALBUM, TYPE_WORK)

def getTypeTitle(type):
    """Return the human-readable and translated title for the given type."""
    return {
            TYPE_NONE: translate("Elements", "<None>"),
            TYPE_ALBUM: translate("Elements", "Album"),
            TYPE_WORK: translate("Elements", "Work"),
            TYPE_COLLECTION: translate("Elements", "Collection")
    }[type]

_typeIcons = {
    TYPE_ALBUM: 'cd.png',
    TYPE_WORK: 'work.png',
    TYPE_COLLECTION: 'cdbox.png'              
}

def getTypeIcon(type):
    """Return an icon as QIcon for the given element type. Return None for TYPE_NONE."""
    if type in _typeIcons:
        return utils.getIcon(_typeIcons[type])
    else: return None

def getTypePixmap(type):
    """Return an icon as QPixmap for the given element type. Return None for TYPE_NONE."""
    if type in _typeIcons:
        return utils.getPixmap(_typeIcons[type])
    else: return None


class Element:
    """Abstract base class for elements (files or containers)."""   
    def __init__(self):
        raise RuntimeError("Cannot instantiate abstract base class Element.")
    
    def isFile(self):
        """Return whether this element is a file."""
        raise NotImplementedError()
    
    def isContainer(self):
        """Return whether this element is a container."""
        raise NotImplementedError()
    
    def isInDb(self):
        """Return whether this element (or rather its version on real level) is stored in the database."""
        from . import reallevel
        return self.id in reallevel._dbIds
    
    def isMajor(self):
        """Return whether the type of this element implies the 'major'-property."""
        return self.type in MAJOR_TYPES
        
    def getTitle(self,usePath=True):
        """Return the title of this element or some dummy title, if the element does not have a title tag.
        If config.options.misc.show_ids is True, the title will be prepended by the element's id.
        If *usePath* is True, the url will be used as title for files without a title tag.
        """
        result = ''
        
        if config.options.misc.show_ids:
            result += "[{}] ".format(self.id)
            
        if tagsModule.TITLE in self.tags:
            result += " - ".join(self.tags[tagsModule.TITLE])
        elif usePath and self.isFile():
            result += str(self.url)
        else: result += translate("Element","<No title>")

        return result
    
    def getAllFiles(self):
        """Return all files below this element. Doesn't eliminate duplicates."""
        if self.isFile():
            yield self
        else:
            for id in self.contents:
                for file in self.level.fetch(id).getAllFiles():
                    yield file
    
    def getStickers(self, type):
        if type not in self.stickers:
            return None
        else:
            result = self.stickers[type]
            if len(result) > 0:
                return result
            else: return None
            
    def hasCover(self):
        # Warning: hasCover returns True if a cover path is stored in the database.
        # This does not mean that the file exists and is readable etc.
        return self.getStickers('COVER') is not None
    
    def getCover(self,size=None):
        paths = self.getStickers('COVER')
        if paths is None:
            return None
        from . import covers
        return covers.get(paths[0],size)
    
    def getCoverPath(self):
        paths = self.getStickers('COVER')
        if paths is None:
            return None
        if os.path.isabs(paths[0]):
            return paths[0]
        else:
            from . import covers
            return os.path.join(covers.COVER_DIR,paths[0])
        
    def inParentLevel(self):
        if self.level.parent is None:
            return None
        elif self.id not in self.level.parent:
            return None
        else: return self.level.parent[self.id]
    
    def equalsButLevel(self, other):
        """Return True if this element equals *other* in all aspects but possibly the level."""
        if self.type != other.type:
            return False
        if self.tags != other.tags:
            return False
        if self.flags != other.flags:
            return False
        if self.stickers != other.stickers:
            return False
        if self.isContainer():
            if self.contents != other.contents:
                return False
        else:
            if self.url != other.url:
                return False
        return True



class Container(Element):
    """Element-subclass for containers. You must specify the level and id and may define additional
    properties using keyword-arguments. Otherwise default values (empty lists etc.) will be used.
    Valid keyword-arguments are type, contents (which must be a ContentList), parents, tags, flags,
    stickers.
    """
    def __init__(self, level, id, type=None, contents=None, parents=None, tags=None, flags=None,
                 stickers=None):
        self.level = level
        self.id = id
        self.level = level
        
        if type is None:
            type = TYPE_NONE
        self.type = type
        if contents is None:
            contents = ContentList()
        self.contents = contents
        if not isinstance(self.contents, ContentList):
            raise TypeError("contents must be a ContentList")
        if parents is None:
            parents = []
        self.parents = parents
        if tags is None:
            tags = tagsModule.Storage()
        self.tags = tags
        if flags is None:
            flags = []
        self.flags = flags
        if stickers is None:
            stickers = {}
        self.stickers = stickers
    
    def copy(self,level=None):
        """Create a copy of this container. Create copies of all attributes. Because contents are stored as
        ids and do not have parent pointers, it is not necessary to copy contents recursively (contrary to
        Wrapper.copy).
        
        If *level* is not None, the copy will have that level as 'level'-attribute.
        Warning: When copying elements from one level to another you might have to correct the parents list.
        """
        return Container(level = self.level if level is None else level,
                         id = self.id,
                         type = self.type,
                         contents = self.contents.copy(),
                         parents = self.parents[:],
                         tags = self.tags.copy(),
                         flags = self.flags[:],
                         stickers = self.stickers.copy())
        
    def isContainer(self):
        return True
    
    def isFile(self):
        return False
    
    def getContents(self):
        """Return a generator yielding the contents of this Container as Element instances (remember that
        self.contents only stores the ids). Elements that have not been loaded yet on this Container's level
        will be loaded."""
        return (self.level.collect(id) for id in self.contents)
    
    def __repr__(self):
        return "Container[{}] with {} elements".format(self.id, len(self.contents))


class File(Element):
    """Element-subclass for files. You must specify the level, id, url and length in seconds of the file.
    You may define additional properties using keyword-arguments. Otherwise default values (empty lists etc.)
    will be used. Valid keyword-arguments are type, parents, tags, flags, stickers.
    """
    def __init__(self, level, id, url, length, **kwargs):
        if not isinstance(id,int) or not isinstance(url, filebackends.BackendURL) \
                or not isinstance(length,int):
            raise TypeError("Invalid type (id,url,length): ({},{},{}) of types ({},{},{})"
                            .format(id,url,length,type(id),type(url),type(length)))
        self.level = level
        self.id = id
        self.level = level
        self.url = url
        self.length = length
        
        self.type = kwargs.get('type', TYPE_NONE)
        self.parents = kwargs.get('parents', [])
        self.tags = kwargs.get('tags', tagsModule.Storage())
        self.flags = kwargs.get('flags', [])
        self.stickers = kwargs.get('stickers', {})
        
    def copy(self, level=None):
        """Create a copy of this file. Create copies of all attributes. If *level* is not None, the copy
        will have that level as 'level'-attribute.
        Warning: When copying elements from one level to another you might have to correct the parents list.
        """
        copy = File(level = self.level if level is None else level,
                    id = self.id,
                    url = self.url,
                    length = self.length,
                    type = self.type,
                    parents = self.parents[:],
                    tags = self.tags.copy(),
                    flags = self.flags[:],
                    stickers = self.stickers.copy())
        if hasattr(self, "specialTags"):
            copy.specialTags = self.specialTags.copy()
        return copy
    
    def isFile(self):
        return True
    
    def isContainer(self):
        return False
    
    def getExtension(self):
        """Return the filename extension of this file."""
        return self.url.extension()
        
    def __repr__(self):
        return "<File[{}] {}>".format(self.id, self.url)
         
         
class ContentList:
    """List that stores a list of ids together with positions (which must be increasing and unique but not
    necessarily the indexes of the corresponding ids). A ContentList can be used like a usual list, except
    that when writing elements via item access is not possible (use append/insert instead).
    """
    def __init__(self, positions=None, ids=None):
        self.ids = ids if ids is not None else []
        self.positions = positions if positions is not None else list(range(1,1+len(self.ids)))
    
    @classmethod
    def fromPairs(cls,pairs):
        """Creates a ContentList from a generator of (position, id) or (position, element) pairs."""
        positions, ids = (list(zp) for zp in zip(*sorted(pairs)))
        ids = [element.id if isinstance(element, Element) else element for element in ids ]
        return ContentList(positions, ids)
    
    @classmethod
    def fromList(cls, elements):
        """Creates a ContentList from a generator of elements or element ids. The positions will simply
        enumerate from 1.
        """
        ids = [element if isinstance(element, int) else element.id for element in elements]
        return ContentList(ids=ids)

    def copy(self):
        """Return a copy of this list."""
        return ContentList(self.positions[:], self.ids[:])
        
    def __len__(self):
        return len(self.ids)
    
    def __contains__(self,id):
        return id in self.ids
    
    def __iter__(self):
        return self.ids.__iter__()
        
    def items(self):
        """Return a generator yielding tuples (position,id) for all ids in the list."""
        return zip(self.positions, self.ids)
    
    def at(self,position):
        """Return the id at position *position*."""
        try:
            return self.ids[self.positions.index(position)]
        except IndexError:
            raise ValueError("In this list there is no element with position {}".format(position))
    
    def positionOf(self,id,start=None):
        """Return the (first) position corresponding to *id*. Raise a ValueError, if *id* is not contained
        in this list. If *start* is given consider only contents with *position* strictly greater than
        *start*.
        """
        if start is None:
            return self.positions[self.ids.index(id)]
        else:
            index = bisect.bisect(self.positions, start)
            return self.positions[self.ids[index:].index(id)+index]
    
    def positionsOf(self, id):
        """Return a list of all positions in which *id* appears."""
        return [pos for (pos, i) in self.items() if i==id]
    
    def append(self, id):
        """Append an id to the list choosing a position which is 1 bigger than the last position."""
        self.ids.append(id)
        if len(self.positions) == 0:
            self.positions.append(1)
        else: self.positions.append(self.positions[-1]+1)
        
    def insert(self, pos, id):
        """Insert an id with a position at the correct index into the list."""
        index = bisect.bisect(self.positions, pos)
        if index > 0 and self.positions[index-1] == pos:  
            raise ValueError("position {} for id {} already in contents ({}, {})"
                             .format(pos, id, self.positions, self.ids))
        self.positions.insert(index, pos)
        self.ids.insert(index, id)
    
    def remove(self,*,pos=None,index=None):
        """Remove an id and its position from the list. You must specify either the position or its index."""
        if pos is not None:
            index = self.positions.index(pos)
        elif index is None:
            raise ValueError("Either of 'pos' or 'index' must be given to ContentList.remove()")
        del self.ids[index]
        del self.positions[index]
        
    def removeAll(self,id):
        """Remove all occurrences of *id* in this list."""
        try:
            index = 0
            while True:
                index = self.ids.find(id,index)
                del self.ids[index]
                del self.positions[index]
        except ValueError:
            pass # all occurrences have been deleted
    
    def shift(self, delta):
        """Shift all positions by *delta*"""
        if len(self) == 0:
            return
        if self.positions[0] + delta  <= 0:
            raise ValueError("Cannot shift positions below 1 (Delta={})".format(delta))
        self.positions = [x+delta for x in self.positions]
    
    def __getitem__(self, i):
        return self.ids[i]
    
    def __setitem__(self, i, pair):
        raise NotImplementedError()
# This is a possible implementation, but maybe it's best that this method is nowhere used.
#        pos, id = pair
#        if (i > 0 and self.positions[i-1] >= pos) or \
#            (i < len(self.positions)-1 and self.positions[i+1] <= pos):
#            raise ValueError("id/position ({},{}) cannot be inserted at index {} because positions "
#                             " must be strictly monotonically increasing."""
#                             .format(id,pos,i))
#        self.positions[i] = pos
#        self.ids[i] = id
    
    def __delitem__(self, i):
        del self.ids[i]
        del self.positions[i]
    
    def __eq__(self, other):
        return self.ids == other.ids and self.positions == other.positions
    
    def __ne__(self, other):
        return self.ids != other.ids or self.positions != other.positions
    
    def __repr__(self):
        return '[{}]'.format(', '.join('{}: {}'.format(*item) for item in self.items()))
