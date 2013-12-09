# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2013 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtCore

from . import BackendURL, BackendFile, urlTypes
from ..core import tags


def init():
    # register the http:// URL scheme
    urlTypes["http"] = HTTPStreamURL


class HTTPStreamURL(BackendURL):
    """A URL type for HTTP streams (e.g. web radio stations).
    """
    CAN_RENAME = True
    CAN_DELETE = False
    
    def __init__(self, urlString):
        assert urlString.startswith("http://")
        super().__init__(urlString)
        self.path = urlString
    
    def toQUrl(self):
        return QtCore.QUrl(self.parsedUrl.geturl())
    
    def renamed(self, newPath):
        """Return a new URL object with path *newPath*, while all other attributes are unchanged."""
        return HTTPStreamURL("http://" + newPath)
    

class HTTPStream(BackendFile):
    DUMMY_TAGS = True
    
    @staticmethod
    def tryLoad(url):
        if url.scheme == "http":
            return HTTPStream(url)
        return None
    
    def __init__(self, url):
        assert url.scheme == "http"
        super().__init__(url)
        self.length = -1
        self.tags = tags.Storage()
        
    def readTags(self):
        pass
    
    def saveTags(self):
        return None
    
    def rename(self, newUrl):
        self.url = newUrl
    
HTTPStreamURL.IMPLEMENTATIONS = [HTTPStream]
