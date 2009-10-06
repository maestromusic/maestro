#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-

import mpd
import muse
import os.path
import sys
class Group():
    
    def __init__(self,name=""):
        self.contents = []
        self.name = name
        self.artist = "Unknown"
    
    def __str__(self):
        ret = self.name + "from: " + self.artist + "\n"
        for file in self.contents:
            ret = ret + "    " + file + "\n"
        return ret

class GroupModule():
    
    def find(self, queries):
        pass
    
    def search(self, queries):
        pass
    
    def list_all(self):
        pass

class AlbumGroupModule():
    
    def __init__(self):
        self.client = mpd.MPDClient()
        self.client.connect(host = muse.MPD_HOST, port = muse.MPD_PORT)
      
      
    def search(self, *queries):
        albums = {}
        for song in self.client.search(*queries):
            try:
                album = song["album"]
                folder,filename = os.path.split(song["file"])
                if not (album,folder) in albums.keys():
                    albums[album,folder] = Group(name=album)
                    albums[album,folder].artist = song["artist"]
                albums[album,folder].contents.append(filename)
                if not albums[album,folder].artist == song["artist"]:
                    albums[album,folder].artist = "Various Artists"
            except KeyError:
                pass
            except TypeError: # this happens if there are multiple album-tags
                print("type error")
                print(album)
                print(folder)
        return albums.values()
    def list_all(self):
        albums = {}
        for song in self.client.listallinfo():
            try:
                album = song["album"]
                folder,filename = os.path.split(song["file"])
                if not (album,folder) in albums.keys():
                    albums[album,folder] = Group(name=album)
                    albums[album,folder].artist = song["artist"]
                albums[album,folder].contents.append(filename)
                if not albums[album,folder].artist == song["artist"]:
                    albums[album,folder].artist == "Various Artists"
                
            except KeyError:
                pass
            except TypeError: # this happens if there are multiple album-tags
                print("type error")
                print(album)
                print(folder)
        return albums.values()
        
omg = AlbumGroupModule()
all_albums = omg.search(*sys.argv[1:])
for alb in all_albums:
    print(alb.name)