# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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
from collections import OrderedDict

from PyQt4 import QtCore

from .. import logging

logger = logging.getLogger(__name__)
translate = QtCore.QCoreApplication.translate

urlTypes = {}
"""Maps scheme to implementing BackendURL subclass, e.g. "file"->RealFile."""

class ParsedUrl:
    def __init__(self, urlString):
        self.scheme, rest = urlString.split("://", 1)
        if '/' in rest:
            self.netloc, rpath = rest.split("/", 1)
        else: self.netloc, rpath = '', rest 
        self.path = "/" + rpath

    def geturl(self):
        return self.scheme + "://" + self.netloc + self.path

    def __str__(self):
        return self.geturl()

def getFile(urlString):
    """Convenience method: first creates an URL and then the according backend file object."""
    url = BackendURL.fromString(urlString)
    return url.getBackendFile()


class BackendURL:
    """Class for URLs defining backend "files" (real files, CDDA tracks, ...).
    
    Objects are immutable to support usage in dictionaries. BackendURLs are uniquely
    identified by their URL string which can be obtained by str()-ing the object.
    """
    
    CAN_RENAME = False
    """A class constant indicating whether this URL type supports renaming in general.
    
    Note that individual files may still be readOnly although CAN_RENAME is True.
    """
    
    CAN_DELETE = False
    """Class constant indicating whether this URL type supports deleting files.""" 
    
    def __init__(self, urlString):
        #  constructor should only be used from subclasses
        assert type(self) is not BackendURL
        self.parsedUrl = ParsedUrl(urlString)
    
    @property
    def scheme(self):
        return self.parsedUrl.scheme
    
    def getBackendFile(self):
        """Create and return a BackendFile object matching this URL.
        
        Tries the classes in self.IMPLEMENTATIONS one by one (via tryLoad()) until the first
        succeeds.
        """
        for cls in self.IMPLEMENTATIONS:
            backendFile = cls.tryLoad(self)
            if backendFile is not None:
                return backendFile
        raise ValueError("No backend succeeded to load {}".format(self))
    
    def extension(self):
        """Return the extension of this file as lower case string."""
        ext = os.path.splitext(str(self))[1]
        if len(ext) > 1:
            return ext[1:].lower()
        return None
    
    def renamed(self, newPath):
        """Return a new URL object with path *newPath*, while all other attributes are unchanged."""
        raise NotImplementedError()
    
    def toQUrl(self):
        """Return a QUrl from this URL. Return None if that is not possible (e.g. weird scheme)."""
        return None

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
        """Create an URL object for the given string. The type is derived from the scheme part."""
        try:
            scheme = urlString.split("://", 1)[0]
            return urlTypes[scheme](urlString)
        except ValueError:
            raise ValueError("Invalid URL (no scheme?): {}".format(urlString)) 
        except KeyError:
            logger.warning("unknown URL {}".format(urlString))
            return UnknownURL(urlString)
            

class UnknownURL(BackendURL):
    
    @property
    def scheme(self):
        return "(!)" + self.parsedUrl.scheme


class BackendFile:
    """Abstract base for a file representation in a specific backend."""
    
        
    DUMMY_TAGS = False
    """If a backend class has DUMMY_TAGS=True, no tags will be read or written to this file."""
    
    @staticmethod
    def tryLoad(url):
        """If the class can load *url*, return an object; otherwise return None."""
        pass
    
    def __init__(self, url):
        """Initialize the backend file, but don't read any tags etc."""
        self.url = url
        self.specialTags = OrderedDict()
        
    def readTags(self):
        """Read the tags which will be available in the *tags* attribute afterwards."""
        raise NotImplementedError()
    
    def saveTags(self):
        """Store any changes made to the tags. May return a sub-storage of failures."""
        raise NotImplementedError()
    
    def rename(self, newPath):
        raise NotImplementedError()
    
    def delete(self):
        raise NotImplementedError()
    
    readOnly = False
    canRename = False
    path = None
    position = None
    length = -1
    
    
class TagWriteError(RuntimeError):
    """An error that is raised when writing tags to disk fails."""
    
    def __init__(self, url, problems=None):
        super().__init__("Error writing tags of {}".format(url))
        self.url = url
        self.problems = problems
        
    def displayMessage(self):
        from ..gui import dialogs
        title = translate("TagWriteError", "Error saving tags")
        msg1 = translate("TagWriteError", "Could not write tags of file {}:\n").format(self.url)
        msgReadonly = translate("TagWriteError", "File is readonly")
        msgProblem = translate("TagWriteError", "Tags '{}' not supported by format").format(self.problems)
        dialogs.warning(title, msg1 + (msgReadonly if self.problems is None else msgProblem))


def changeTags(changes):
    """Change tags of files. If an error occurs, all changes are undone and a TagWriteError is raised.
    
    *changes* is a dict mapping elements or BackendFiles to TagDifferences. If the dict contains elements
    only the corresponding BackendFiles will be changed! This method does not touch the element instances
    or the database. Containers will be skipped.
    All BackendFiles contained in the dict must already have loaded their tags.
    """
    from ..core import elements
    doneFiles = []
    rollback = False
    problems = None
    for elementOrFile, diff in changes.items():
        if isinstance(elementOrFile, elements.Element):
            if not elementOrFile.isFile():
                continue
            backendFile = elementOrFile.url.getBackendFile()
            backendFile.readTags()
        else:
            backendFile = elementOrFile
        
        if backendFile.DUMMY_TAGS:
            continue
        if backendFile.readOnly:
            problemUrl = backendFile.url
            rollback = True
            break
        
        currentFileTags = backendFile.tags.copy()
        diff.apply(backendFile, withoutPrivateTags=True)
        #logger.debug('changing tags of {}: {}'.format(backendFile.url, diff))
        problems = backendFile.saveTags()
        if problems:
            problemUrl = backendFile.url
            backendFile.tags = currentFileTags
            backendFile.saveTags()
            rollback = True
        else:
            doneFiles.append((backendFile,diff))
            
    if rollback:
        for backendFile,diff in doneFiles:
            diff.revert(backendFile.tags, withoutPrivateTags=True)
            backendFile.saveTags()
        raise TagWriteError(problemUrl, problems)
