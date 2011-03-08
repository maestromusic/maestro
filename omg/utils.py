#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2010 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
#

def mapRecursively(f,aList):
    """Take <aList> which may contain (recursively) further lists and apply <f> to each element in these lists (except the lists). Return a copy a <aList> with the results."""
    result = []
    for item in aList:
        if isinstance(item,list):
            result.append(mapRecursively(f,item))
        else: result.append(f(item))
    return result


class OrderedDict(dict):
    """Ordered subclass of dictionary which allows inserting key: value-mappings at arbitrary positions - in contrast to collections.OrderedDict. By default new mappings will be appended at the end of the order. Use the insert*-methods to insert somewhere else.

    Note that currently the views returned by keys(), values() and items() do not take the order into account."""
    def __init__(self):
        """Create an empty ordered dictionary."""
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
        """Insert the mapping <key>: <value> at the position <pos>."""
        if key in self:
            raise ValueError("Key '{}' is already contained in this OrderedDict.".format(key))
        self._keyList.insert(pos,key)
        self.__setitem__(key,value)

    def changeKey(self,oldKey,newKey):
        """Change the key <oldKey> into <newKey>."""
        if newKey in self:
            raise ValueError("Key '{}' is already contained in the OrderedDict.")
        pos = self._keyList.index(oldKey)
        self._keyList[pos] = newKey
        self[newKey] = self[oldKey]
        dict.__delitem__(self,oldKey) # Do not use del as it would try tor remove oldKey from _keyList

    def index(self,key):
        """Return the position of <key>."""
        return self._keyList.index(key)

    def insertAfter(self,posKey,key,value):
        """Insert the mapping <key>: <value> into this OrderedDict after the key <posKey>."""
        self.insert(self.index(posKey)+1,key,value)

    def insertBefore(self,posKey,key,value):
        """Insert the mapping <key>: <value> into this OrderedDict before the key <posKey>."""
        self.insert(self.index(posKey),key,value)
