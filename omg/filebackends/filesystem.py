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

"""This module implements the BackendFile and BackendURL for files on the local filesystem."""

import os.path

import taglib

from . import BackendFile, BackendURL, urlTypes
from .. import logging, utils
from ..core import tags

logger = logging.getLogger(__name__)


class RealFile(BackendFile):
    """A normal file that is accessed directly on the filesystem."""
    
    @staticmethod
    def tryLoad(url):
        """Returns a RealFile instance if the url protocol fits and the file exists.
        """
        if url.proto == 'file' and os.path.exists(url.absPath):
            return RealFile(url)
        return None
    
    def __init__(self, url):
        assert url.proto == "file"
        super().__init__(url)
        
    def readTags(self):
        """Load the tags from disk using pytaglib.
        
        If the file has a TRACKNUMBER tag, its value is stored in the position attribute of
        this object, but won't be contained in self.tags. Likewise, discnumber is ignored.
        """
        
        self._taglibFile = taglib.File(self.url.absPath) 
        self.tags = tags.Storage()
        self.ignoredTags = dict()
        if "TRACKNUMBER" in self._taglibFile.tags:
            #  Only consider the first tracknumber ...
            self.position = utils.parsePosition(self._taglibFile.tags["TRACKNUMBER"][0]) 
        for key, values in self._taglibFile.tags.items():
            key = key.lower()
            if key in ["tracknumber", "discnumber"]:
                self.ignoredTags[key] = values
            else:
                tag = tags.get(key)
                validValues = []
                for string in values:
                    try:
                        validValues.append(tag.valueFromString(string, crop=True))
                    except ValueError:
                        logger.error("Invalid value for tag '{}' found: {}".format(tag.name,string))
                if len(validValues) > 0:
                    self.tags.add(tag, *validValues)
        
    @property
    def length(self):
        return self._taglibFile.length

    @property
    def readOnly(self):
        if hasattr(self, '_taglibFile'):
            return self._taglibFile.readOnly
        return False
    
    def rename(self, newUrl):
        # TODO: handle open taglib file references
        os.renames(self.url.absPath, newUrl.absPath)
        self.url = newUrl
        
    def saveTags(self):
        """Save what's in self.tags to the file.
        
        In addition to the tags in self.tags, any ignored tags (TRACKNUMBER etc.) that were read
        using readTags() will be stored in to the file such that they aren't lost.
        """
        self._taglibFile.tags = dict()
        for tag, values in self.ignoredTags.items():
            self._taglibFile.tags[tag.upper()] = values
        for tag, values in self.tags.items():
            values = [tag.fileFormat(value) for value in values]
            self._taglibFile.tags[tag.name.upper()] = values
        unsuccessful = self._taglibFile.save()
        del self._taglibFile
        if len(unsuccessful) > 0:
            ret = tags.Storage()
            for key, values in unsuccessful.items():
                ret[key.upper()] = values
            return ret
        return None


class FileURL(BackendURL):
    """A standard URL pointing to the local filesystem; the form is file:///path/to/file.flac.
    
    Note that the path is always understood as being relative to the music base directory.
    """
    
    CAN_RENAME = True
    IMPLEMENTATIONS = [ RealFile ]
    
    def __init__(self, urlString):
        if "://" not in urlString:
            urlString = "file:///" + utils.relPath(urlString)
        super().__init__(urlString)
        self.path = self.parsedUrl.path[1:]
        self.absPath = utils.absPath(self.path)
        
    def renamed(self, newPath):
        """Return a new FileURL with the given *newPath* as path."""
        return FileURL("file:///" + newPath)


# register the file:// URL protocol
urlTypes["file"] = FileURL