#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-

import omg
import sys
import pprint
import mpd
import os

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
    for dirpath, dirnames, filenames in os.walk(path):
        albums_in_this_directory = {}
        for f in filenames:
            try:
                t = omg.read_tags_from_file(os.path.abspath(os.path.join(dirpath,f)))
            except RuntimeError as e:
                print("Ecxeption while trying to read tags from file, skipping...\n({0})".format(e))
                continue
            if "album" in t:
                album = t["album"][0]
                if not album in albums_in_this_directory:
                    albums_in_this_directory[album] = {}
                albums_in_this_directory[album][os.path.join(dirpath,f)] = t
            else:
                print("Here is a file without album: {0}".format(os.path.join(dirpath,f)))
        for name,album in albums_in_this_directory.items():
            #name = album generate_album_name(album)
            print("I found an album '{0}' in directory '{1}' containing {2} files.".format(name,dirpath,len(album)))

walk(sys.argv[1])
