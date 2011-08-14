#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2010 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
#
import subprocess, pickle, re, os

from .. import tags, logging
from ..utils import absPath
from ..config import options
import cutags

logger = logging.getLogger(__name__)

def get(path):
    """Create a RealFile-instance for the given path, which may be a relative or absolute path."""
    if not os.path.isabs(path):
        path = absPath(path)
    return UFile(path)


class TagIOError(IOError):
    """Exception if reading or writing tags fails."""
    pass


class RealFile:
    """Abstract base class for file classes. Currently there is only one subclass, though."""
    def __init__(self,path):
        """Create a file for the given path."""
        self.path = path
        self.tags = tags.Storage()
        self.length = None
        self.position = None

    def read(self):
        """Read all information, like tags, length, etc. from the filesystem"""
        raise NotImplementedError()

    def remove(self,tags):
        """Remove the tags in the given list from the file. If a tag from the list is not contained in the file, skip it without warning."""
        raise NotImplementedError()

    def saveTags(self):
        """Store the tags that are currently present in the tags attribute in the file."""
        raise NotImplementedError()
        
    def savePosition(self):
        """Store the position that is currently stored in self.position or remove it from the file if self.position is None."""
        raise NotImplementedError()
        
    def save(self):
        """Store tags and position in the file."""
        self.saveTags()
        self.savePosition()
    
    def _valueFromString(self,tag,value):
        """Convert the string <value> to the preferred format of <tag> (e.g. convert "2010" to a FlexiDate-instance). Return None and log a message if conversion fails."""
        try:
            if tag.type == tags.TYPE_DATE:
                # Chop of the time part of values of the form
                # YYYY-MM-DD HH:MM:SS
                # YYYY-MM-DD HH:MM
                # YYYY-MM-DD HH
                # These formats are allowed in the ID3 specification and used by Mutagen
                if len(value) in (13,16,19) and re.match("\d{4}-\d{2}-\d{2} \d{2}(:\d{2}){0,2}$",value) is not None:
                    value = value[:10]
                    
            return tag.type.valueFromString(value)
        except ValueError:
            logger.warning("Found invalid tag-value '{}' for tag {} in file {}".format(value,tag,self.path))
            return None 
        
    def _parsePosition(self,string):
        """Parse a string like "7" or "2/5" to a (integer) position. If <string> has the form "2/5", the first number will be returned."""
        string = string.strip()
        if string.isdecimal():
            return int(string)
        # Watch for positions of the form 2/5
        elif re.match('\d+\s*/\s*\d+$',string):
            return int(string.split('/')[0])
        else: return None
        
class UFile(RealFile):
    def __init__(self, path):
        RealFile.__init__(self, path)
        self._f = None
        
    def _ensureFileIsLoaded(self):
        if self._f is None:
            self._f = cutags.File(self.path)
    
    def read(self):
        self._ensureFileIsLoaded()
        self.ignoredTags = dict()
        self.tags = tags.Storage()
        if "TRACKNUMBER" in self._f.tags:
            self.position = self._parsePosition(self._f.tags["TRACKNUMBER"][0])  # Further tracknumbers are ignored
        for key,values in self._f.tags.items():
            if key.lower() in ["tracknumber", "discnumber"]:
                self.ignoredTags[key] = values
                continue
            tag = tags.get(key.lower())
            values = [self._valueFromString(tag,value) for value in values]
            values = list(filter(lambda x: x is not None,values))
            if len(values) > 0:
                self.tags.addUnique(tag, *values)
    
    def saveTags(self):
        self._ensureFileIsLoaded()
        self._f.tags = dict()
        for tag, values in self.ignoredTags.items():
            self._f.tags[tag] = values
        for tag,values in self.tags.items():
            values = [str(value) for value in values]
            self._f.tags[tag.name.upper()] = values
        self._f.save()
    
    def savePosition(self):
        self._ensureFileIsLoaded()
        self._f.tags["TRACKNUMBER"] = str(self.position)
        self._f.save()
    
    def remove(self, tags):
        self._ensureFileIsLoaded()
        changed = False
        for t in tags:
            if self._f.tags.contains(t.name.upper()):
                del self._f.tags[t.name.upper()]
                changed = True
        if changed:
            self._f.save()
            
