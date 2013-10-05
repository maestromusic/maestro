# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2013 Martin Altmayer, Michael Helmling
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

from collections import OrderedDict
import os.path

from PyQt4 import QtCore

import taglib

from . import BackendFile, BackendURL, urlTypes
from .. import logging, utils
from ..core import tags

logger = logging.getLogger(__name__)
translate = QtCore.QCoreApplication.translate

def init():
    # register the file:// URL scheme
    urlTypes["file"] = FileURL


class RealFile(BackendFile):
    """A normal file that is accessed directly on the filesystem."""
    
    @staticmethod
    def tryLoad(url):
        """Returns a RealFile instance if the url scheme fits and the file exists."""
        if url.scheme == 'file' and os.path.exists(url.absPath):
            return RealFile(url)
        return None
    
    def __init__(self, url):
        assert url.scheme == "file"
        super().__init__(url)
        
    specialTagNames = "tracknumber", "compilation", "discnumber"
           
    def readTags(self):
        """Load the tags from disk using pytaglib.
        
        Special tags (tracknumber, compilation, discnumber) are stored in the "specialTags" attribute.
        """
        
        self._taglibFile = taglib.File(self.url.absPath, applyID3v2Hack=True) 
        self.tags = tags.Storage()
        self.specialTags = OrderedDict()
        for key, values in self._taglibFile.tags.items():
            key = key.lower()
            if key in self.specialTagNames:
                self.specialTags[key] = values
            elif tags.isValidTagName(key):
                tag = tags.get(key)
                validValues = []
                for string in values:
                    try:
                        validValues.append(tag.convertValue(string, crop=True))
                    except tags.TagValueError:
                        logger.error("Invalid value for tag '{}' found: {}".format(tag.name, string))
                if len(validValues) > 0:
                    self.tags.add(tag, *validValues)
            else:
                logger.error("Invalid tag name '{}' found : {}".format(key, self.url))
        
    @property
    def length(self):
        return self._taglibFile.length

    @property
    def readOnly(self):
        if hasattr(self, '_taglibFile'):
            return self._taglibFile.readOnly
        fileAtt = os.stat(self.url.absPath)
        import stat
        return not (fileAtt[stat.ST_MODE] & stat.S_IWUSR)

    
    def rename(self, newUrl):
        # TODO: handle open taglib file references
        if os.path.exists(newUrl.absPath):
            raise OSError("Target exists.")
        os.renames(self.url.absPath, newUrl.absPath)
        from ..core import levels
        levels.real.emitFilesystemEvent(renamed=((self.url, newUrl),))
        self.url = newUrl
    
    def delete(self):
        """Deletes this file from disk. Also removes empty directories."""
        os.remove(self.url.absPath)
        directory = os.path.dirname(self.url.absPath)
        if len(os.listdir(directory)) == 0:
            os.removedirs(directory)
        from ..core import levels
        levels.real.emitFilesystemEvent(deleted=(self.url,))
        
    def saveTags(self):
        """Save what's in self.tags to the file.
        
        In addition to the tags in self.tags, any ignored tags (TRACKNUMBER etc.) that were read
        using readTags() will be stored in to the file such that they aren't lost.
        
        If some tags cannot be saved due to restrictions of the underlying metadata format, those
        tags/values that remain unsaved will be returned.
        """
        self._taglibFile.tags = dict()
        for tag, values in self.specialTags.items():
            self._taglibFile.tags[tag.upper()] = values
        for tag, values in self.tags.items():
            values = [tag.fileFormat(value) for value in values]
            self._taglibFile.tags[tag.name.upper()] = values
        unsuccessful = self._taglibFile.save()
        ret = {key.upper(): values for key,values in unsuccessful.items()}
        from ..core import levels
        levels.real.emitFilesystemEvent(modified=(self.url,))
        return ret


class FileURL(BackendURL):
    """A standard URL pointing to the local filesystem; the form is file:///path/to/file.flac.
    
    Note that the path is always understood as being relative to the music base directory.
    """
    
    CAN_RENAME = True
    CAN_DELETE = True
    IMPLEMENTATIONS = [ RealFile ]
    
    def __init__(self, urlString):
        if "://" not in urlString:
            urlString = "file:///" + utils.relPath(urlString)
        super().__init__(urlString)
    
    @property
    def path(self):
        return self.parsedUrl.path[1:]
    
    @property
    def absPath(self):
        return utils.absPath(self.path)
    
    def renamed(self, newPath):
        """Return a new FileURL with the given *newPath* as path."""
        return FileURL("file:///" + newPath)
    
    def toQUrl(self):
        """Return a QUrl from this URL. Return None if that is not possible (e.g. weird scheme)."""
        return QtCore.QUrl('file://'+self.absPath)
