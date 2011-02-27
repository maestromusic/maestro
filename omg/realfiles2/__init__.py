#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2010 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
#
import subprocess, pickle, re

from omg import config, tags, absPath
from omg.config import options
import cutags

def get(path,absolute=False):
    """Create a RealFile-instance for the given path, which must be absolute if the second parameter is true and otherwise relative to the music directory."""
    if not absolute:
        path = absPath(path)
    #return MutagenFile(path)
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
        if not tag.isIndexed():
            return value
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
        self.tags = tags.Storage()
        if "TRACKNUMBER" in self._f.tags:
            self.position = self._parsePosition(self._f.tags["TRACKNUMBER"][0])  # Further tracknumbers are ignored
        for key,values in self._f.tags.items():
            tag = tags.get(key.lower())
            if tag.isIgnored():
                continue
            values = [self._valueFromString(tag,value) for value in values]
            values = list(filter(lambda x: x is not None,values))
            if len(values) > 0:
                self.tags.addUnique(tag, *values)
    def saveTags(self):
        self._ensureFileIsLoaded()
        self._f.tags = dict()
        for tag,values in self.tags.items():
            values = [str(value) for value in values]
            if tag.name.upper() not in self._f.tags:
                self._f.tags[tag.name.upper()] = values
            else: self._f.tags[tag.name.upper()].extend(values) # May happen if there exist an IndexedTag and an OtherTag with the same name...actually this should never happen
        self._f.store()
    def savePosition(self):
        self._ensureFileIsLoaded()
        self._f.tags["TRACKNUMBER"] = str(self.position)
        self._f.store()
    def remove(self, tags):
        self._ensureFileIsLoaded()
        changed = False
        for t in tags:
            if self._f.tags.contains(t.name.upper()):
                del self._f.tags[t.name.upper()]
                changed = True
        if changed:
            self._f.store()
            
                
        
class MutagenFile(RealFile):
    """This class implements the methods of RealFile by opening the tags_python2-script (which is written in Python 2 and hence can use Mutagen) in a subprocess and communicating pickled data over stdout and stdin."""
    def _openProc(self):
        """Create the tags_python2-subprocess."""
        return subprocess.Popen(options.misc.tags_python2_cmd,
                                stdout=subprocess.PIPE,stdin=subprocess.PIPE)

    def _transmit(self,proc,data,error):
        """Transmit <data> to the subprocess <proc>, then fetch the result and return it. If an error in the subprocess occurs, raise a TagIOError with the given message (among other stuff)."""
        pickle.dump(data,proc.stdin,protocol=2)
        proc.stdin.flush()
        data = pickle.load(proc.stdout)
        if data is 1:
            raise TagIOError(error+"\n"+proc.stderr.read().decode())
        else: return data

    def _importTags(self,tagDict):
        """Convert tag-dictionaries as returned by the tags_python2-script (tagname -> list of tag-values as strings) to tag-dicts as used in omg (tag-instance -> list of tag-values in the correct type). This method will remove values which cannot be converted."""
        result = tags.Storage()
        for key,values in tagDict.items():
            tag = tags.get(key)
            if tag.isIgnored():
                continue
            # Try to convert the values and remove those where conversion failed
            values = [self._valueFromString(tag,value) for value in values]
            values = list(filter(lambda x: x is not None,values))
            
            if len(values) > 0:
                result.addUnique(tag,*values)
        return result



    def _exportTags(self):
        """Convert the tags in this file to the dict format used by the tags_python2-script (tagnames -> list of string values)."""
        result = dict()
        for tag,values in self.tags.items():
            values = [str(value) for value in values]
            if tag.name not in result:
                result[tag.name] = values
            else: result[tag.name].extend(values) # May happen if there exist an IndexedTag and an OtherTag with the same name...actually this should never happen
        return result



    def read(self):
        proc = self._openProc()
        data = {'command': 'read', 'path': self.path}
        result = self._transmit(proc,data,"Error reading tags from file '{0}'".format(data))
        if "tracknumber" in result['tags']:
            self.position = self._parsePosition(result['tags']["tracknumber"][0])  # Further tracknumbers are ignored
        else: self.position = None
        self.tags = self._importTags(result["tags"])
        self.length = result["length"]
        proc.terminate()

    def remove(self,tagsToRemove):
        proc = self._openProc()
        data = {'command': 'remove', 'path': self.path, 'tags': {tag.name for tag in tagsToRemove}}
        self._transmit(proc,data,"Error removing the following tags from file '{}': {}".format(self.path,tagsToRemove))
        proc.terminate()
        
    def saveTags(self):
        proc = self._openProc()

        # Read the keys of all tags
        data = {'command': 'keys','path': self.path}
        tagKeys = self._transmit(proc,data,"Error reading tagkeys from file '{}'".format(self.path))

        # Remove the tags which are neither contained in self.tags nor ignored
        exportedTags = self._exportTags()
        tagsToRemove = [tag for tag in tagKeys if tag not in exportedTags and not tags.get(tag).isIgnored()]
        data = {'command': 'remove', 'path': self.path, 'tags': tagsToRemove}
        self._transmit(proc,data,"Error removing the following tags from file '{}': {}".format(self.path,tagsToRemove))
        
        # Store the tags
        data = {'command': 'store', 'path': self.path, 'tags': exportedTags}
        self._transmit(proc,data,"Error storing the following tags in file '{}': {}".format(self.path,self.tags.keys()))

        proc.terminate()

    def savePosition(self):
        proc = self._openProc()
        if self.position is not None:
            data = {'command': 'store', 'path': self.path, 'tags': {'tracknumber': [str(self.position)]}}
            self._transmit(proc,data,"Error storing the tracknumber {} in file '{}'".format(self.position,self.path))
        else:
            data = {'command': 'remove', 'path': self.path, 'tags': ['tracknumber']}
            self._transmit(proc,data,"Error removing the tracknumber from file '{}'".format(self.path))
        proc.terminate()
