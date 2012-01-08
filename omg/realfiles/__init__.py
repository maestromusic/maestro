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

import subprocess, pickle, re, os

from .. import tags, logging
from ..utils import absPath
from ..config import options
logger = logging.getLogger(__name__)

def get(path, ignoreUnknownTags = False):
    """Create a RealFile-instance for the given path, which may be a relative or absolute path."""
    if not os.path.isabs(path):
        path = absPath(path)
    return rfClass(path, ignoreUnknownTags)

def parsePosition(string):
        """Parse a string like "7" or "2/5" to a (integer) position. If <string> has the form "2/5", the first number will be returned."""
        string = string.strip()
        if string.isdecimal():
            return int(string)
        # Watch for positions of the form 2/5
        elif re.match('\d+\s*/\s*\d+$',string):
            return int(string.split('/')[0])
        else: return None
        
class RealFile:
    """Abstract base class for file classes."""
    def __init__(self,path):
        """Create a file for the given path. Raises IOError if the file cannot be read."""
        self.path = path
        self.tags = tags.Storage()
        self.length = None
        self.position = None

    
    def read(self):
        """Read the tags of the file and convert them according to a tags.Storage object according to
        OMG's internal rules. This might raise an UnknownTagException."""
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

rfClass = None
try:
    import cutags    
    class UFile(RealFile):
        """A RealFile implementation using cutags, the wrapper for UTagLib."""
        def __init__(self, path):
            RealFile.__init__(self, path)
            self._f = None
            
        def _ensureFileIsLoaded(self):
            if self._f is None:
                self._f = cutags.File(self.path)
        
        def _parseAndAdd(self, key, values):
            tag = tags.get(key)
            vals = []
            for value in values:
                value = self._valueFromString(tag, value)
                if value is not None and value not in vals:
                    vals.append(value)
            if len(vals) > 0:
                self.tags.add(tag, *vals)
                
        def read(self):
            self._ensureFileIsLoaded()
            self.ignoredTags = dict() # dict storing tags which are ignored but not deleted by omg, i.e. {track,disc}number
            self.tags = tags.Storage()
            if "TRACKNUMBER" in self._f.tags:
                self.position = parsePosition(self._f.tags["TRACKNUMBER"][0])  # Further tracknumbers are ignored
            toDelete = []
            for key,values in self._f.tags.items():
                key = key.lower()
                if key in ["tracknumber", "discnumber"]:
                    self.ignoredTags[key] = values
                elif key in options.tags.always_delete:
                    # remove question after some testing
                    from ..gui.dialogs import question
                    if question('really delete tag?',
                                '"always_delete" tag *{0}* found in {1}. Really delete?'.format(key, self.path)):
                        toDelete.append(key)
                else:
                    try:
                        self._parseAndAdd(key, values)
                    except tags.UnknownTagError as e:
                        e.values = values
                        self.remove(toDelete)
                        raise e
            self.remove(toDelete)        
            self.length = self._f.length
            
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
        
        def remove(self, tagList):
            if isinstance(tagList, str) or isinstance(tagList, tags.Tag):
                tagList = [tagList]
            self._ensureFileIsLoaded()
            changed = False
            for t in tagList:
                if  str(t).upper() in self._f.tags:
                    logger.debug("removing tag {0} from {1}".format(t, self.path))
                    del self._f.tags[str(t).upper()]
                    changed = True
            if changed:
                self._f.save()
    rfClass = UFile
    logger.info('loaded UTagLib realfiles backend')
except ImportError:
    pass

try:
    import taglib
    class TagLibFile(RealFile):
        """A RealFile implementation using pytaglib, the wrapper for taglib."""
        def __init__(self, path, ignoreUnknownTags = False):
            # TODO: this is due to a bug in taglib, which
            # crashes on opening non-existing OGG files
            # instead of just reporting an error.
            if not os.path.exists(path):
                raise OSError('file does not exist')
            RealFile.__init__(self, path)
            self._f = taglib.File(path)
            self.ignoreUnknownTags = ignoreUnknownTags
        
        def read(self):
            self.tags = tags.Storage()
            self.ignoredTags = dict()
            if "TRACKNUMBER" in self._f.tags:
                self.position = parsePosition(self._f.tags["TRACKNUMBER"][0])  # Further tracknumbers are ignored
            toDelete = []
            for key,values in self._f.tags.items():
                key = key.lower()
                if key in ["tracknumber", "discnumber"]:
                    self.ignoredTags[key] = values
                elif key in options.tags.always_delete:
                    toDelete.append(key)
                else:
                    try:
                        self._parseAndAdd(key, values)
                    except tags.UnknownTagError as e:
                        if self.ignoreUnknownTags:
                            logger.warning('Ignored unknown tag {} on reading file'.format(key))
                        else:
                            e.values = values
                            self.remove(toDelete)
                            raise e
                        
            self.remove(toDelete)        
            self.length = self._f.length
            
        def _parseAndAdd(self, key, values):
            tag = tags.get(key)
            vals = []
            for value in values:
                value = self._valueFromString(tag, value)
                if value is not None and value not in vals:
                    vals.append(value)
            if len(vals) > 0:
                self.tags.add(tag, *vals)
            
            
        def saveTags(self, reallySave = True):
            self._f.tags = dict()
            for tag, values in self.ignoredTags.items():
                self._f.tags[tag] = values
            for tag,values in self.tags.items():
                values = [str(value) for value in values]
                self._f.tags[tag.name.upper()] = values
            if reallySave:
                self._f.save()
        
        def savePosition(self, reallySave = True):
            self._ensureFileIsLoaded()
            self._f.tags["TRACKNUMBER"] = str(self.position)
            if reallySave:
                self._f.save()
        
        def save(self):
            """Reimplemented for efficiency: Only call self._f.save() once."""
            self.saveTags(False)
            self.savePosition()
        
        def remove(self, tagList):
            if isinstance(tagList, str) or isinstance(tagList, tags.Tag):
                tagList = [tagList]
            changed = False
            for t in tagList:
                if  str(t).upper() in self._f.tags:
                    logger.debug("removing tag {0} from {1}".format(t, self.path))
                    del self._f.tags[str(t).upper()]
                    changed = True
            if changed:
                self._f.save()
                
    rfClass = TagLibFile
    logger.info('loaded TagLib realfiles backend')
except ImportError:
    pass

if not rfClass:
    logger.error('Could not load any realfiles backend!! :(')