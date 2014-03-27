# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2013-2014 Martin Altmayer, Michael Helmling
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

from omg import filebackends
from omg.core import tags


class AudioCDURL(filebackends.BackendURL):
    """URLs for tracks on Audio CDs.
    
    The scheme is the following: audiocd://<discid>.<tracknr>/<destinedPath>
    
    where <destinedPath> is the path within the music directory to which the file, once ripped,
    will be moved.
    """
    
    CAN_RENAME = True
    IMPLEMENTATIONS = []
    
    def __init__(self, urlString):
        super().__init__(urlString)
        self.discid, tracknr = self.parsedUrl.netloc.rsplit(".", 1)
        self.tracknr = int(tracknr)
        self.targetPath = self.parsedUrl.path[1:]
    
    @property
    def path(self):
        return self.targetPath
    
    def renamed(self, newPath):
        return AudioCDURL("audiocd://{}/{}".format(self.parsedUrl.netloc, newPath))
    
    def toQUrl(self):
        return None


class AudioCDTrack(filebackends.BackendFile):

    readOnly = False
    
    @staticmethod
    def tryLoad(url):
        if url.scheme == "audiocd":
            return AudioCDTrack(url)
        
    def __init__(self, url):
        assert url.scheme == "audiocd"
        super().__init__(url)
        
    def readTags(self):
        self.tags, self.length = tags.Storage(), 0
    
    def saveTags(self):
        pass
    
    def rename(self, newPath):
        pass
    
    def delete(self):
        pass
        
AudioCDURL.IMPLEMENTATIONS = [AudioCDTrack]