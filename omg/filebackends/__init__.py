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
class InvalidFileProtocol(Exception):
    pass

fileBackends = {}
def registerBackend(cls):
    global fileBackends
    for proto in cls.protocols:
        if proto not in fileBackends:
            fileBackends[proto] = []
        fileBackends[proto].append(cls)

def unregisterBackend(cls):
    global fileBackends
    for proto in cls.protocols:
        fileBackends[proto].remove(cls)

def get(string):
    url = urlparse(string)
    if url.scheme not in fileBackends:
        raise InvalidFileProtocol("Protcol {} not known".format(url.scheme))
    for cls in fileBackends[url.scheme]:
        backendFile = cls.tryLoad(url)
        if backendFile is not None:
            return backendFile
    raise ValueError("No backend succeeded to load {}".format(string))
    
class BackendFile:
    
    def __init__(self, url):
        """Initialize the backend file and read tags etc."""
        self.url = url
    
    def save(self):
        """Store any changes made to the tags."""
        pass
    
    @staticmethod
    def tryLoad(url):
        pass
    
    readOnly = False
    position = None
    length = -1
    
    