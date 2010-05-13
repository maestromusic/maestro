#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from PyQt4 import QtCore
from omg import mpclient, database, models

class PlaylistElement(models.Element):
    """Subclass of models.Element that is used for the files in syncplaylist.Playlist. In addition to the id it stores the element's path and length."""
    def __init__(self,id=None,path=None):
        """Create a PlaylistElement with the given id and/or path. If one of the arguments is None, it is calculated from the other one. If both are None a ValueError is raised. If only path is given but there is no file with this path in the database a LookupError is raised."""
        if id is None and path is None:
            raise ValueError()
        if id is not None:
            models.Element.__init__(self,id)
            self.path,self.length = database.get().query("SELECT path,length FROM files WHERE container_id = ?",id)[0]
        else: # path is not None
            self.path = path
            row = database.get().query("SELECT container_id,length FROM files WHERE path = ?",path).getSingleRow()
            if row is None: # path was not found in the database
                raise LookupError()
            models.Element.__init__(self,row[0])
            self.length = row[1]
    
    def isFile(self):
        return True
        
    def getPath(self):
        return self.path
    
    def getLength(self):
        return self.length
        
    def __str__(self):
        return ("<PlaylistElement {0} at {1}>".format(self.id,self.path))


class Playlist(QtCore.QObject):
    filesInserted = QtCore.pyqtSignal(int,int)
    filesRemoved = QtCore.pyqtSignal(int,int)
    listReset = QtCore.pyqtSignal()
    
    def __init__(self):
        QtCore.QObject.__init__(self)
        self._list = []
        
    def synchronize(self,mpdList):
        pos = 0
        while pos < len(self._list) or pos < len(mpdList):
            if pos >= len(self._list): # => pos < len(mpdList):
                # Add rest to self._list
                self._list.extend([PlaylistElement(path=path) for path in mpdList[pos:]])
                self.filesInserted.emit(pos,len(mpdList)-1)
                return
            elif pos >= len(mpdList): # => pos < len(self._list):
                # Remove rest from self._list
                playlistLength = len(self._list)
                del self._list[pos:]
                self.filesRemoved.emit(pos,playlistLength - 1)
                return
            # pos < len(self._list) and mpdPos < len(list)
            
            # If the entries coincide, skip them
            if mpdList[pos] == self._list[pos].path:
                pos = pos + 1
                continue

            # Ok now the elements at position pos are different, but at least one list is not exhausted, so check first whether elements have been inserted and then whether elements have been removed.
            
            #print("Elements at position {0} are different.".format(pos))
            
            # If elements have been inserted in mpdList, self._list[pos] must appear somewhere later in mpdList:
            try:
                matchPos = mpdList.index(self._list[pos].path,pos+1)
                #print("Found at position {0} in mpdList".format(matchPos))
                self._list[pos:pos] = [PlaylistElement(path=path) for path in mpdList[pos:matchPos]]
                self.filesInserted.emit(pos,matchPos-1)
                pos = matchPos + 1 # Skip the inserted files and the file at matchPos which coincides clearly
                continue
            except ValueError: pass
            
            try:
                matchPos = _playlistIndex(self._list,mpdList[pos],pos+1)
                #print("Found at position {0} in playlist".format(matchPos))
                del self._list[pos:matchPos]
                self.filesRemoved.emit(pos,matchPos-1)
                pos = pos + 1 # Since the files in between have been deleted this position coincides now
                continue
            except ValueError: pass
            
            # Something happened that is too complicated for me...so reset the whole list
            self._list = [PlaylistElement(path=path) for path in mpdList]
            self.listReset.emit()
            return
    
    def get(self):
        return self._list


def _playlistIndex(playlist,path,startPos):
    while startPos < len(playlist):
        if playlist[startPos].path == path:
            return startPos
        else: startPos = startPos + 1
    raise ValueError()