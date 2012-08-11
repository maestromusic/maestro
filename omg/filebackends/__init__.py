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

from urllib.parse import urlparse
import os.path

class InvalidFileProtocol(Exception):
    pass

class BackendURL:
    """Class for URLs defining backend "files" (real files, CDDA tracks, ...).
    
    Objects are immutable to support usage in dictionaries. BackendURLs are uniquely
    identified by their URL string which can be obtained by str()-ing the object.
    """
    
    CAN_RENAME = False
    """A class constant indicating whether this URL type supports renaming in general.
    
    Note that individual files may still be readOnly although CAN_RENAME is True.
    """
    
    def __init__(self, urlString):
        """Don't call this directly; use the static "fromString" instead."""
        self.parsedUrl = urlparse(urlString)
    
    @property
    def proto(self):
        return self.parsedUrl.scheme
    
    def getBackendFile(self):
        for cls in self.IMPLEMENTATIONS:
            backendFile = cls.tryLoad(self)
            if backendFile is not None:
                return backendFile
        raise ValueError("No backend succeeded to load {}".format(self))
    
    def extension(self):
        ext = os.path.splitext(str(self))[1]
        if len(ext) > 1:
            return ext[1:].lower()
        return None
    
    def renamed(self, newPath):
        """Return a new URL object with pat h*newPath*, while all other attributes are unchanged.
        """ 
        pass

    def __hash__(self):
        return hash(str(self))
    
    def __eq__(self, other):
        return type(self) is type(other) and str(self) == str(other)
    
    def __neq__(self, other):
        return type(self) is not type(other) or str(self) != str(other)
    
    def __str__(self):
        return self.parsedUrl.geturl()
    
    def __repr__(self):
        return "{}({})".format(self.__class__.__name__, str(self))
    
    @staticmethod
    def fromString(urlString):
        """Create an URL object for the given string. The type is derived from the protocol part."""
        proto = urlString.split("://", 1)[0]
        return urlTypes[proto](urlString)

urlTypes = {}

def getFile(urlString):
    """Convenience method: first gets URL and then the backend file object."""
    url = BackendURL.fromString(urlString)
    return url.getBackendFile()
    
class BackendFile:
    
    @staticmethod
    def tryLoad(url):
        pass
    
    def __init__(self, url):
        """Initialize the backend file, but don't read any tags etc."""
        self.url = url
        
    def readTags(self):
        """Read the tags which will be available in the *tags* attribute afterwards."""
        pass
    
    def saveTags(self):
        """Store any changes made to the tags."""
        pass
    
    def rename(self, newPath):
        pass
    
    def computeHash(self):
        pass
    
    readOnly = False
    canRename = False
    path = None
    position = None
    length = -1
    
    