# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2012-2014 Martin Altmayer, Michael Helmling
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

from ... import filebackends, player
from ...filebackends import filesystem


class MPDURL(filebackends.BackendURL):
    
    scheme = "mpd"
    CAN_RENAME = False
    IMPLEMENTATIONS = []
    
    def __init__(self, urlString):
        super().__init__(urlString)
        self.profile = self.parsedUrl.netloc
        self.path = self.parsedUrl.path[1:]
        
    def asLocalFile(self):
        mpdProfile = player.profileCategory.get(self.profile)
        return filesystem.FileURL("file://" + os.path.join(mpdProfile.path, self.path))
        
    def toQUrl(self):
        return self.asLocalFile().toQUrl()


class MPDFile(filebackends.BackendFile):

    readOnly = True
    
    @staticmethod
    def tryLoad(url):
        #TODO support multiple urls
        #rf = filesystem.RealFile.tryLoad(url.asLocalFile())
        #if rf is not None:
        #    return rf
        return MPDFile(url)
        
    def __init__(self, url):
        assert url.scheme == "mpd"
        super().__init__(url)
        
    def readTags(self):
        mpdProfile = player.profileCategory.get(self.url.profile)
        self.tags, self.length = mpdProfile.getInfo(self.url.path)
        
MPDURL.IMPLEMENTATIONS = [MPDFile]
