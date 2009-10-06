#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-

import mpde
import sys
import pprint
import mpd

client = mpde.mpdClient()
def generate_album_name(files):
    """Generates a string name for an album consisting of the given files. Very intelligent. """
    
    album = None
    artist = None
    composer = None
    date = None
    various_artists = False
    various_composers = False
    for file in files:
        try:
            result = client.find("filename", file)
            tags = result[0]
            if len(result) > 1:
                print("W T F?")
                input()
            if not various_artists:
                if 'artist' in tags:
                    if artist and not tags['artist'] == artist: #whoops, different artists
                        various_artists = True
                    else:
                        artist = tags['artist']
            if not various_composers:
                if 'composer' in tags:
                    if composer and not tags['composer'] == composer: #different composers
                        various_composers = True
                    else:
                        composer = tags['composer']
            if 'album' in tags:
                album = tags['album']
            if 'date' in tags:
                date = tags['date']
        except mpd.CommandError as e:
            print(e)
            print("file: {0}".format(file))
    if various_artists or artist == None:
        if various_composers or composer == None:
            ret =  album
        else:
            ret =  "{0}: {1}".format(composer, album)
    else: # unique artist
        if various_composers or composer == None:
            ret =  "{0} - {1}".format(artist, album)
        else:
            ret =  "{0}: {1} by {2}".format(artist, album, composer)
    if date:
        ret += " ({0})".format(date)
    return ret
           

def walk(path):
    elements = client.lsinfo(path)
    albums_in_this_directory = {}
    for el in elements:
        if "directory" in el:
            # this means the element is a subdirectory of path
            walk(el["directory"])
        else:
            # we have a file
            if "album" in el:
                if not el["album"] in albums_in_this_directory:
                    albums_in_this_directory[el["album"]] = []
                albums_in_this_directory[el["album"]].append(el["file"])
            else:
                print("Here is a file without album: {0}".format(el["file"]))
    core = mpde.MPDe()
    for album in albums_in_this_directory.values():
        name = generate_album_name(album)
        print("I found an album '{0}' in directory '{1}' containing {2} files.".format(name,path,len(album)))
        core.add_file_container(name,album)
            
walk(sys.argv[1])