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

import datetime, os, functools
from omg import config
from omg import constants
from PyQt4 import QtGui, QtCore
from collections import OrderedDict


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

def ranges(lst):
    def helper(lst, first, cur, result):
        if len(lst) == 0:
            return result + [(first,cur)]
        if lst[0][1] == cur + 1:
            return helper(lst[1:], first, cur+1, result)
        return helper(lst[1:], lst[0][1], lst[0][1], result + [(first,cur)])
    if len(lst) <= 1:
        return list(map(lambda x: (x,x), lst))
    return helper(list(enumerate(lst[1:])), lst[0], lst[0], list())


def walk(element):
    """A tree iterator for elements, inspired by os.walk: Returns a tuple (element, contents)
    where contents may be modified in-place to influence further processing."""
    contents = element.getContents()[:]
    yield element, contents
    for child in contents:
        for x in walk(child):
            yield x

def groupFilePaths(paths):
    """Takes a list of file paths, splits them into dirname and basename, and groups
    them by the dirname."""
    filesByFolder = {}
    for path in paths:
        dir, filename = os.path.split(path)
        if dir not in filesByFolder:
            filesByFolder[dir] = []
        filesByFolder[dir].append(filename)
    return filesByFolder
            
def hasKnownExtension(file):
    """Return True if the given path has a known extension (i.e., appears in options.main.extension).
    Does **not** check whether the file actually exists, is readable, etc."""
    s = file.rsplit(".", 1)
    if len(s) == 1:
        return False
    else:
        return s[1].lower() in config.options.main.extensions


def relPath(file):
    """Returns the relative path of a music file against the collection base path."""
    if os.path.isabs(file):
        return os.path.relpath(file, config.options.main.collection)
    else:
        return file


def absPath(file):
    """Returns the absolute path of a music file inside the collection directory, if it is not absolute
    already."""
    if not os.path.isabs(file):
        return os.path.join(config.options.main.collection, file)
    else:
        return file


def collectFiles(paths):
    """Finds all music files below the given *paths*. The output is a dict mapping subdirectory paths to
    lists of contained music files."""
    
    filePaths ={}
    def add(file, parent = None):
        
        if not hasKnownExtension(file):
            return
        dir = parent or os.path.dirname(file)
        if dir not in filePaths:
            filePaths[dir] = []
        filePaths[dir].append(file)
    for path in paths:
        if os.path.isfile(path):
            add(path)
        else:
            for parent, dirs, files in os.walk(path):
                for f in sorted(files):
                    add(os.path.join(parent, f), parent)
                dirs.sort()
    return filePaths

def getIcon(name):
    """Return a QIcon for the icon with the given name."""
    if not QtCore.QFile.exists(':omg/icons/' + name):
        print(name + ' does not exist')
    return QtGui.QIcon(":omg/icons/" + name)

def getPixmap(name):
    """Return a QPixmap for the icon with the given name."""
    return QtGui.QPixmap(":omg/icons/" + name)

class FlexiDate(object):
    """A FlexiDate is a date which can store a date consisting simply of a year or of a year and a month or of
    year, month and day. OMG uses this class to store tags of type date, where most users will only specify a
    year, but some may give month and day, too.

    Note that while MySQL's DATE type can store dates where day and month may be unspecified, neither
    datetime.date nor QDate can. Thus binding FlexiDates to SQL-queries does not work. For this reason
    FlexiDates are stored as integers in the DB (confer :meth:`FlexiDate.toSql` and
    :meth:`FlexiDate.fromSql`).

    The parameters may be anything that can be converted to :func:`int`. *month* and *day* may also be
    ``None``. If *month* or *day* are 0 or ``None`` they are regarded as unspecified. Note that you must not
    give a nonzero *day* if *month* is zero or ``None``. This method raises a :exc:`ValueError` if 
    conversion to :func:`int` fails or if the date is invalid (confer :class:`datetime.date`).
    """
    def __init__(self, year, month = None, day = None):
        self.year = int(year)
        
        if month == 0 or month is None: # cannot pass None to int(), so we have to check for it here
            self.month = None
            if day is not None and day != 0:
                raise ValueError("Cannot store a day if month is None.")
        elif 1 <= month <= 12:
            self.month = int(month)
        else: raise ValueError("Invalid month given.")
        
        if day == 0 or day is None:
            self.day = None
        else:
            self.day = int(day)
            datetime.date(self.year,self.month,self.day) # Check date
    
    @staticmethod
    def strptime(string):
        """Parse FlexiDates from strings in one of the formats ``'YYYY-mm-dd'`` or ``'YYYY-mm'`` or ``'YYYY'``.
        Raise a :exc:`ValueError` if that fails."""
        if not isinstance(string,str):
            raise TypeError("Argument must be a string.")
        try:
            return FlexiDate(*map(int,string.split("-")))
        except TypeError as e:
            # A TypeError is raised if the number of arguments doesn't fit. In our case that's more a kind of ValueError.
            raise ValueError(e.message)
    
    def strftime(self, format = ("{Y:04d}-{m:02d}-{d:02d}", "{Y:04d}-{m:02d}", "{Y:04d}")):
        """Format the FlexiDate according to the given format. *format* must be a 3-tuple of
        format strings, where the first one if used if year, month and day are specified,
        the second one is used if only the day misses, and the third one is used if there
        is only a year. The format strings are python format strings, where Y=year, m=month, d=day."""
        if self.month:
            if self.day:
                format = format[0]
            else: format = format[1]
        else: format = format[2]
        return format.format(Y=self.year, m=self.month, d=self.day)
        
    def toSql(self,maximum=False):
        """Convert this FlexiDate to an int as used to store it in the database."""
        result = 10000*self.year
        if self.month is not None:
            result += 100*self.month
            if self.day is not None:
                result += self.day
        return result

    def toMaximalSql(self):
         return 10000*self.year + 100*12 + 31
         
    @staticmethod
    def fromSql(value):
        """Create a FlexiDate from an int as used to store FlexiDates in the database."""
        from omg import database
        if database.isNull(value):
            return None
        try:
            value = int(value)
            return FlexiDate(value // 10000,(value // 100) % 100,value % 100)
        except ValueError as e:
            raise ValueError("Cannot create a FlexiDate from value {}: {}".format(value,e))

    def __str__(self):
        return self.strftime()

    def __repr__(self):
        if self.month:
            if self.day:
                return "FlexiDate({},{},{})".format(self.year,self.month,self.day)
            else: return "FlexiDate({},{})".format(self.year,self.month)
        else: return "FlexiDate({})".format(self.year)
        
    def __lt__(self, other):
        if not isinstance(other,FlexiDate):
            return NotImplemented
        for a,b in ((self.year,other.year),(self.month,other.month),(self.day,other.day)):
            if a == b:
                continue
            if a is None:
                return True
            if b is None:
                return False
            return a < b
        else: return False # Equality

    def __gt__(self, other):
        if not isinstance(other,FlexiDate):
            return NotImplemented
        return other.__lt__(self)
    
    def __le__(self, other):
        return self == other or self.__lt__(other)
    
    def __ge__(self, other):
        return self == other or self.__gt__(other)
        
    def __eq__(self, other):
        return isinstance(other,FlexiDate) and\
            self.year == other.year and self.month == other.month and self.day == other.day
        
    def __ne__(self,other):
        return not isinstance(other,FlexiDate) or\
            self.year != other.year or self.month != other.month or self.day != other.day

    def __hash__(self):
        return id(self)
    
    
class OrderedDict(dict):
    """Ordered subclass of :class:`dict` which allows inserting key-value-mappings at arbitrary positions --
    in contrast to :class:`collections.OrderedDict`. By default new mappings will be appended at the end of
    the order. Use the insert*-methods to insert somewhere else.
    
    Note that currently the views returned by :meth:`keys <dict.keys>`, :meth:`values <dict.values>` and
    :meth:`items <dict.items>` do not respect the order."""
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
        return OrderedDictItems(self)

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
    """OrderedDict.items returns an instance of this class to ensure that the items are returned in the
    correct order."""
    def __init__(self,oDict):
        self.oDict = oDict
    
    def __len__(self):
        return len(self.oDict)
    
    def __contains__(self,item):
        return item in self.oDict
    
    def __iter__(self):
        """Return an iterator which will iterate over the keys in the correct order."""
        for key in self.oDict._keyList:
            yield key,self.oDict[key]

    
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
