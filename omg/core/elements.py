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

import os.path, bisect

from PyQt4 import QtCore
translate = QtCore.QCoreApplication.translate

from . import tags as tagsModule
from .. import config

class Element:
    """Abstract base class for elements (files or containers)."""   
    def __init__(self):
        raise RuntimeError("Cannot instantiate abstract base class Element.")

    def isInDB(self):
        """Return whether this element is contained in the database (as opposed to e.g. external files in
        the playlist or newly created containers in the editor).
        """
        return self.id > 0
    
    def isFile(self):
        """Return whether this element is a file."""
        raise NotImplementedError()
    
    def isContainer(self):
        """Return whether this element is a container."""
        raise NotImplementedError()
    
    def getTitle(self,usePath=True):
        """Return the title of this element or some dummy title, if the element does not have a title tag.
        If config.options.misc.show_ids is True, the title will be prepended by the element's id.
        If *usePath* is True, the path will be used as title for files without a title tag.
        """
        result = ''
        
        if hasattr(self,'id') and config.options.misc.show_ids:
            result += "[{}] ".format(self.id)
            
        if tagsModule.TITLE in self.tags:
            result += " - ".join(self.tags[tagsModule.TITLE])
        elif usePath and self.isFile():
            result += self.path
        else: result += translate("Element","<No title>")

        return result
    

class Container(Element):
    """Element-subclass for containers. You must specify the level and id and whether this Container is
    major. Keyword-arguments that are not specified will be set to empty lists/tag.Storage instances.
    Note that *contents* must be a ContentList.
    """
    def __init__(self, level, id, major,*, contents=None, parents=None, tags=None, flags=None):
        self.level = level
        self.id = id
        self.level = level
        self.major = major
        if contents is not None:
            if type(contents) is not ContentList:
                raise TypeError("contents must be a ContentList")
            self.contents = contents
        else: self.contents = ContentList()
        if parents is not None:
            self.parents = parents
        else: self.parents = []
        if tags is not None:
            self.tags = tags
        else: self.tags = tagsModule.Storage()
        if flags is not None:
            self.flags = flags
        else: self.flags = []
    
    def copy(self):
        """Create a copy of this container. Create copies of all attributes. Because contents are stored as
        ids and do not have parent pointers, it is not necessary to copy contents recursively (contrary to
        Wrapper.copy).
        """
        return Container(level = self.level,
                         id = self.id,
                         major = self.major,
                         contents = self.contents.copy(),
                         parents = self.parents[:],
                         tags = self.tags.copy(),
                         flags = self.flags[:])
        
    def isContainer(self):
        return True
    
    def isFile(self):
        return False
    
    def getContents(self):
        """Return a generator yielding the contents of this Container as Element instances (remember that
        self.contents only stores the ids). Elements that have not been loaded yet on this Container's level
        will be loaded."""
        return (self.level.get(id) for id in self.contents)
    
    def __repr__(self):
        return "Container[{}] with {} elements".format(self.id, len(self.contents))


class File(Element):
    """Element-subclass for files. You must specify the level, id, path and length in seconds of the file.
    Keyword-arguments that are not specified will be set to empty lists/tag.Storage instances.
    """
    def __init__(self, level, id, path, length,*, parents=None, tags=None, flags=None):
        if not isinstance(id,int) or not isinstance(path,str) or not isinstance(length,int):
            raise TypeError("Invalid type (id,path,length): ({},{},{}) of types ({},{},{})"
                            .format(id,path,length,type(id),type(path),type(length)))
        self.level = level
        self.id = id
        self.level = level
        self.path = path
        self.length = length
        
        if parents is not None:
            self.parents = parents
        else: self.parents = []
        if tags is not None:
            self.tags = tags
        else: self.tags = tagsModule.Storage()
        if flags is not None:
            self.flags = flags
        else: self.flags = []
        
    def copy(self):
        return File(level = self.level,
                    id = self.id,
                    path = self.path,
                    length = self.length,
                    parents = self.parents[:],
                    tags = self.tags.copy(),
                    flags = self.flags[:])
    
    def isFile(self):
        return True
    
    def isContainer(self):
        return False
    
    def getExtension(self):
        """Return the filename extension of this file."""
        ext = os.path.splitext(self.path)[1]
        if len(ext) > 0:
            return ext[1:].lower() # remove the dot
        else: return None
        
    def __repr__(self):
        return "<File[{}] {}>".format(self.id, self.path)


class ContentList:
    """List that stores a list of ids together with positions (which must be increasing and unique but not
    necessarily the indexes of the corresponding ids). On item access the list will return tuples containing
    the id and the position.
    """
    def __init__(self):
        self.positions = []
        self.ids = []
    
    def copy(self):
        """Return a copy of this list."""
        result = ContentList()
        result.ids = self.ids[:]
        result.positions = self.positions[:]
        return result
    
    def append(self,id):
        """Append an id to the list choosing a position which is 1 bigger than the last position."""
        self.ids.append(id)
        if len(self.positions) == 0:
            self.positions.append(1)
        else: self.positions.append(self.positions[-1]+1)
        
    def __len__(self):
        return len(self.ids)
    
    def __getitem__(self, i):
        raise RuntimeError("don't use this function, it is ambiguous and thus dangerous")
        return self.ids[i], self.positions[i]
    
    def __delitem__(self, i):
        del self.ids[i]
        del self.positions[i]
        
    def __setitem__(self, i, pos, id):
        if (i > 0 and self.positions[i-1] >= pos) or \
            (i < len(self.positions)-1 and self.positions[i+1] <= pos):
            raise ValueError("id/position ({},{}) cannot be inserted at index {} because positions "
                             " must be strictly monotonically increasing."""
                             .format(id,pos,i))
        self.positions[i] = pos
        self.ids[i] = id
    
    def __contains__(self,id):
        return id in self.ids
    
    def getPosition(self,id,start=None):
        """Return the position corresponding to *id*. Raise a ValueError, if *id* is not contained in this
        list. If *start* is given consider only contents with *position* strictly greater than *start*.
        """
        if start is None:
            return self.positions[self.ids.index(id)]
        else:
            index = bisect.bisect(self.positions, start)
            return self.positions[self.ids[index:].index(id)+index]
    
    def getId(self, position):
        """Return the id at position *position*."""
        return self.ids[self.positions.index(position)]
    
    def insert(self, pos, id):
        """Insert an id with a position at the correct index into the list."""
        index = bisect.bisect(self.positions, pos)
        if index > 0 and self.positions[index-1] == pos:  
            raise ValueError("position {} for id {} already in contents ({}, {})"
                             .format(pos, id, self.positions, self.ids))
        self.positions.insert(index, pos)
        self.ids.insert(index, id)
    
    def remove(self,pos=None,index=None):
        """Remove an id and its position from the list. You must specify either the position or its index."""
        if pos is not None:
            index = self.positions.index(pos)
        elif index is None:
            raise ValueError("Either of 'pos' or 'index' must be given to ContentList.remove()")
        del self.ids[index]
        del self.positions[index]
    
    def items(self):
        """Return a generator yielding tuples (position,id) for all ids in the list."""
        return zip(self.positions, self.ids)
    
    def shift(self, delta):
        """Shift all positions by *delta*"""
        if len(self) == 0:
            return
        # ensure position doesn't drop below 1 after the shift
        assert self.positions[0] + delta  > 0
        self.positions = [x+delta for x in self.positions]
    
    def __eq__(self, other):
        return self.ids == other.ids and self.positions == other.positions
    
    def __ne__(self, other):
        return self.ids != other.ids or self.positions != other.positions
    
    def __str__(self):
        return '[{}]'.format(', '.join('{}: {}'.format(self.positions[i],self.ids[i])
                                       for i in range(len(self.positions))))
         
