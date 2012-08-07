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

import re, os

from .. import config, logging, utils
from ..core import tags

logger = logging.getLogger(__name__)


def get(path):
    """Create a RealFile-instance for the given path, which may be a relative or absolute path."""
    if not os.path.isabs(path):
        path = utils.absPath(path)
    return rfClass(path)


def parsePosition(string):
        """Parse a string like "7" or "2/5" to a (integer) position. If *string* has the form "2/5", the
        first number will be returned."""
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
        
        self.read()
  
    def read(self):
        """Read the tags of the file and convert them according to a tags.Storage object according to
        OMG's internal rules."""
        raise NotImplementedError()
    
    def remove(self,tags):
        """Remove the tags in the given list from the file. If a tag from the list is not contained in the 
        file, skip it without warning."""
        raise NotImplementedError()

    def saveTags(self):
        """Store the tags that are currently present in the tags attribute in the file."""
        raise NotImplementedError()
        
    def savePosition(self):
        """Store the position that is currently stored in self.position or remove it from the file if
        self.position is None."""
        raise NotImplementedError()
        
    def save(self):
        """Store tags and position in the file."""
        self.saveTags()
        self.savePosition()


rfClass = None


try:
    import taglib
    
    class TagLibFile(RealFile):
        """A RealFile implementation using pytaglib, the wrapper for taglib."""
        def __init__(self, path):
            # TODO: this is due to a bug in taglib, which
            # crashes on opening non-existing OGG files
            # instead of just reporting an error.
            if not os.path.exists(path):
                raise OSError('file does not exist')
            RealFile.__init__(self, path)
            self._f = taglib.File(path)
        
        def read(self):
            self.tags = tags.Storage()
            self.ignoredTags = dict()
            if "TRACKNUMBER" in self._f.tags:
                # Further tracknumbers are ignored
                self.position = parsePosition(self._f.tags["TRACKNUMBER"][0]) 
            for key,values in self._f.tags.items():
                key = key.lower()
                if key in ["tracknumber", "discnumber"]:
                    self.ignoredTags[key] = values
                else:
                    tag = tags.get(key)
                    validValues = []
                    for string in values:
                        try:
                            validValues.append(tag.valueFromString(string,crop=True))
                        except ValueError:
                            logger.error("Invalid value for tag '{}' found: {}".format(tag.name,string))
                    if len(validValues) > 0:
                        self.tags.add(tag, *validValues)
                               
            self.length = self._f.length
            
        def saveTags(self, reallySave=True):
            self._f.tags = dict()
            for tag, values in self.ignoredTags.items():
                self._f.tags[tag.upper()] = values
            for tag, values in self.tags.items():
                values = [tag.fileFormat(value) for value in values]
                self._f.tags[tag.name.upper()] = values
            if reallySave:
                self._f.save()
        
        def savePosition(self, reallySave=True):
            self._f.tags["TRACKNUMBER"] = str(self.position)
            if reallySave:
                self._f.save()
        
        def save(self):
            """Reimplemented for efficiency: Only call self._f.save() once."""
            self.saveTags(reallySave=False)
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
    