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

import os.path

import taglib

from . import BackendFile, registerBackend
from .. import logging, utils
from ..core import tags

logger = logging.getLogger(__name__)
        
class RealFile(BackendFile):
    """A normal file that is accessed directly on the filesystem."""
    
    protocols = ["file"]
    
    @staticmethod
    def tryLoad(url):
        if url.scheme == 'file' and os.path.exists(utils.absPath(url.path[1:])):
            return RealFile(url)
        return None
            
    def __init__(self, url):
        """Create a file for the given path. Raises IOError if the file cannot be read."""
        super().__init__(url)
        self.relpath = url.path[1:] # remove leading slash
        self.abspath = utils.absPath(self.relpath)
        self._read()
        
    def _read(self):
        self._taglibFile = taglib.File(self.abspath) 
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
        return self._taglibFile.readOnly
    
    def save(self):
        self._taglibFile.tags = dict()
        for tag, values in self.ignoredTags.items():
            self._taglibFile.tags[tag.upper()] = values
        for tag, values in self.tags.items():
            values = [tag.fileFormat(value) for value in values]
            self._taglibFile.tags[tag.name.upper()] = values
        unsuccessful = self._taglibFile.save()
        if len(unsuccessful) > 0:
            ret = tags.Storage()
            for key, values in unsuccessful.items():
                ret[key.upper()] = values
            return ret
        return None
    
registerBackend(RealFile)