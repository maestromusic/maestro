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

from omg import filebackends
from omg.core import tags


class AudioCDURL(filebackends.BackendURL):
    
    scheme = "audiocd"
    CAN_RENAME = False
    IMPLEMENTATIONS = []
    
    def __init__(self, urlString):
        super().__init__(urlString)
        self.discid = self.parsedUrl.netloc
        self.tracknr = int(self.parsedUrl.path[1:])
        
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
        
AudioCDURL.IMPLEMENTATIONS = [AudioCDTrack]