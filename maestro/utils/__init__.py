# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2015 Martin Altmayer, Michael Helmling
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

import locale, functools, re
from PyQt5 import QtCore, QtGui, QtWidgets
from .. import config

# include submodules so that 'import utils' suffices to support 'utils.strings. ...'
from . import files, images, strings, worker
from .flexidate import FlexiDate


def mapRecursively(f,aList):
    """Take *aList* which may contain (recursively) further lists and apply *f* to each element in these
    lists (except the lists). Return a copy of *aList* with the results::

            >>> mapRecursively(lambda x: 2*x,[1,2,[3,4],[5]])
            [2,4,[6,8],[10]]
            
    \ """
    result = []
    for item in aList:
        if isinstance(item,list):
            result.append(mapRecursively(f,item))
        else: result.append(f(item))
    return result


def parsePosition(string):
    """Parse a string like "7" or "2/5" to a (integer) position.
    
    If *string* has the form "2/5", the first number will be returned."""
    string = string.strip()
    if string.isdecimal():
        return int(string)
    elif re.match('\d+\s*/\s*\d+$',string):
        return int(string.split('/')[0])
    else:
        return None


class InverseDifference:
    """Wrapper around a diff object (e.g. TagDifference) that acts like the inverse diff object."""
    def __init__(self,difference):
        self._diff = difference
        
    def apply(self,element, *args, **kwargs):
        self._diff.revert(element, *args, **kwargs)
        
    def revert(self,element, *args,**kwargs):
        self._diff.apply(element, *args, **kwargs)
        
    def getAdditions(self):
        return self._diff.getRemovals()

    def getRemovals(self):
        return self._diff.getAdditions()
    

#DEPRECATED use utils.images.getIcon instead
def getIcon(name):
    """Return a QIcon for the icon with the given name."""
    return QtGui.QIcon(":maestro/icons/" + name)


#DEPRECATED use utils.images.getPixmap instead
def getPixmap(name):
    """Return a QPixmap for the icon with the given name."""
    return QtGui.QPixmap(":maestro/icons/" + name)
    
    
class OrderedDict(dict):
    """Ordered subclass of :class:`dict` which allows inserting key-value-mappings at arbitrary positions --
    in contrast to :class:`collections.OrderedDict`. By default new mappings will be appended at the end of
    the order. Use the insert*-methods to insert somewhere else.
    
    Note that currently the views returned by :meth:`keys <dict.keys>` and :meth:`values <dict.values>` do
    not respect the order.
    """
    def __init__(self):
        dict.__init__(self)
        self._keyList = []

    def __setitem__(self,key,value):
        if key not in self._keyList:
            self._keyList.append(key)
        dict.__setitem__(self,key,value)

    def __delitem__(self,key):
        self._keyList.remove(key)
        dict.__delitem__(self,key)

    def __iter__(self):
        """Return an iterator which will iterate over the keys in the correct order."""
        return iter(self._keyList)

    def insert(self,pos,key,value):
        """Insert the mapping ``key: value`` at the position *pos*."""
        if key in self:
            raise ValueError("Key '{}' is already contained in this OrderedDict.".format(key))
        self._keyList.insert(pos,key)
        self.__setitem__(key,value)

    def extend(self,items):
        """Extend this dict by *items* which may be either a dict or a list of key-value pairs."""
        if isinstance(items,dict):
            items = items.items()
        for key,value in items:
            self.__setitem__(key,value)
            
    def changeKey(self,oldKey,newKey,sameHash=False):
        """Change the key *oldKey* into *newKey*. Usually this works only if *newKey* is not contained in
        this dict yet. In particular this methods fails, if *oldKey* and *newKey* have the same hash as
        *newKey* is then considered to be contained in the dict. If you set the optional parameter *sameHash*
        to True, this method will replace the keys even if they have the same hash.
        """
        if newKey in self and not sameHash:
            raise ValueError("Key '{}' is already contained in the OrderedDict.".format(newKey))
        pos = self._keyList.index(oldKey)
        self._keyList[pos] = newKey
        value = self[oldKey]
        dict.__delitem__(self,oldKey) # Do not use del as it would try tor remove oldKey from _keyList
        self[newKey] = value

    def index(self,key):
        """Return the position of *key*."""
        return self._keyList.index(key)

    def insertAfter(self,posKey,key,value):
        """Insert the mapping ``key: value`` after the key *posKey*."""
        self.insert(self.index(posKey)+1,key,value)

    def insertBefore(self,posKey,key,value):
        """Insert the mapping ``key: value`` before the key *posKey*."""
        self.insert(self.index(posKey),key,value)

    def items(self):
        return OrderedDictItems(self,self._keyList)
    
    def keys(self):
        return self._keyList
    
    def values(self):
        return OrderedDictValues(self,self._keyList)

    def copy(self):
        result = OrderedDict()
        result.update(self)
        result._keyList = self._keyList[:]
        return result
        
    @staticmethod
    def fromItems(items):
        """Create an OrderedDict from a list of key->value pairs."""
        result = OrderedDict()
        for key,value in items:
            result[key] = value
        return result
    

class OrderedDictItems:
    """This class provides a view as provided by the builtin method dict.items. The difference is that the
    in which (key,value)-pairs are returned is determined by the list of keys *keyList*.
    
    Warning: If the keys of the underlying dict change, the list *keyList* must be changed accordingly.
    """
    def __init__(self,aDict,keyList):
        self.aDict = aDict
        self.keyList = keyList
    
    def __len__(self):
        return len(self.aDict)
    
    def __contains__(self,kvTuple):
        k,v = kvTuple
        return k in self.aDict and self.aDict[k] == v
    
    def __iter__(self):
        """Return an iterator which will iterate over the keys in the correct order."""
        for key in self.keyList:
            yield key,self.aDict[key]


class OrderedDictValues:
    """This class provides a view as provided by the builtin method dict.values. The difference is that the
    in which values are returned is determined by the list of keys *keyList*.
    
    Warning: If the keys of the underlying dict change, the list *keyList* must be changed accordingly.
    """
    def __init__(self,aDict,keyList):
        self.aDict = aDict
        self.keyList = keyList
    
    def __len__(self):
        return len(self.aDict)
    
    def __contains__(self,value):
        return dict.contains(self.aDict,value)
    
    def __iter__(self):
        """Return an iterator which will iterate over the keys in the correct order."""
        for key in self.keyList:
            yield self.aDict[key]
            

@functools.total_ordering
class PointAtInfinity:
    """Depending on the parameter *plus* this object is either bigger or smaller than any other object
    (except for other instances of PointAtInfinity with the same parameter). This is useful in key-functions
    for list.sort. The advantage compared to ``float("inf")`` is that the latter only compares to numbers.
    """
    def __init__(self,plus=True):
        self.plus = plus
        
    def __le__(self,other):
        return not self.plus
    
    def __eq__(self,other):
        return isinstance(other,PointAtInfinity) and other.plus == self.plus

    def __str__(self):
        return "{}{}".format('+' if self.plus else '-', '∞')


def search(sequence, f):
  """Return the first item in *sequence* where f(item) is True."""
  for item in sequence:
      if f(item): 
          return item
  return None
  
def find(aList, item):
    """Return the index of the first occurrence of *item* in *aList*. Return -1 if *item* is not found."""
    for i,x in enumerate(aList):
        if x == item:
            return i
    else: return -1  
    
def rfind(aList, item):
    """Return the index of the last occurrence of *item* in *aList*. Return -1 if *item* is not found."""
    for i,x in enumerate(reversed(aList)):
        if x == item:
            return len(aList)-1-i
    else: return -1
    