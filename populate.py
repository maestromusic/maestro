#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-
# Copyright 2009 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
# populate.py

import omg
import sys
import pprint
import mpd
import os
from functools import reduce

def do_album(album):
    """Processes an album, which should be of type omg.Container."""
    
    album_name = album[list(album.keys())[0]].tags["album"][0] # O M G :)
    
    common_tags = reduce(lambda x,y: x & y, [set(album[a].tags.keys()) for a in album]) - set(["tracknumber","title"])
    common_tag_values = {}
    different_tags=set()
    for file in album.values():
        tags = file.tags
        for tag in common_tags:
            if tag not in common_tag_values:
                common_tag_values[tag] = tags[tag]
            if common_tag_values[tag] != tags[tag]:
                different_tags.add(tag)
    same_tags = common_tags - different_tags
    for tag in same_tags:
        album.tags[tag]=common_tag_values[tag]

    # build a name
    if max([len(common_tag_values[x]) for x in  set(["composer","artist","album"]) & same_tags])>1:
        name = "Sorry, you have multiple tags in {composer,artist,album}, please have a look"
    else:
        if 'composer' in common_tags:
            if 'composer' in same_tags and 'artist' in same_tags:
                name = "{0}: {1} ({2})".format(common_tag_values["composer"][0],album_name,common_tag_values["artist"][0])
            elif 'composer' in same_tags: #'artist' not in same_tags
                name = "{0} - {1}".format(common_tag_values["composer"][0],album_name)
            elif 'artist' in same_tags: ##composer not in same_tags
                name = "{0} - {1}".format(common_tag_values["artist"][0],album_name)
            else:
                name = album_name
        else:
            if 'artist' in same_tags:
                name = "{0} - {1}".format(common_tag_values["artist"][0],album_name)
            else:
                name = album_name
    album.name = name
    accepted = False
    while not accepted:
        print("+++++ I SUGGEST: +++++")
        print("1]  Name of the Container: {0}".format(album.name))
        print("2]  Contents:")
        for track in sorted(album.keys()):
            print("      {0}".format(os.path.basename(album[track].path)))
        print("3]  Tags (common to all files):")
        for tag in album.tags:
            for v in album.tags[tag]:
                print("    {0}={1}".format(tag,v))
        if len(different_tags) > 0:
            print("4]  !!TAKE CARE: Tags which are NOT equal on all songs!!:")
            for tag in different_tags:
                print("    {0}".format(tag))
        
        have_extratags = False
        for track in sorted(album.keys()):
            extratags = set(album[track].tags.keys()) - set(album.tags.keys()) - set(["tracknumber","title"])
            if len(extratags) > 0:
                if not have_extratags:
                    print("5] !!TAKE CARE!!: We have some extra tags in some files:")
                    extratags = True
                print("The file '{0}' has extra tags:".format(path))
                for tag in extratags:
                    print("  {0}={1}".format(tag,album[track].tags[tag]))
        ans = input("What do you want me to do? Accept [Enter] or further examine a section [1-6]?")
        if ans=="1":
            album.name = input("Enter new name:\n")
        elif ans=="":
            accepted = True
    print("you have accepted. spast ...")
    album.tags = {x:common_tag_values[x] for x in same_tags}
    omg.add_file_container(container=album)


def walk(path):
    for dirpath, dirnames, filenames in os.walk(path):
        albums_in_this_directory = {}
        for filename in [os.path.join(dirpath, f) for f in filenames]:
            if omg.id_from_filename(filename):
                continue #file already exists
            try:
                t = omg.read_tags_from_file(os.path.abspath(filename))
            except RuntimeError as e:
                print("Ecxeption while trying to read tags from file, skipping...\n({0})".format(e))
                raise e
            if "album" in t:
                album = t["album"][0]
                file = omg.File(filename, tags=t, length=t.length)
                if not album in albums_in_this_directory:
                    albums_in_this_directory[album] = omg.Container()
                if "tracknumber" in t:
                    trkn = int(t["tracknumber"][0])
                    albums_in_this_directory[album][trkn] = file
                else:
                    if 0 in albums_in_this_directory[album]:
                        print("More than one files in this album without tracknumber, don't know what to do: \n{0}".format(filename))
                    else:
                        albums_in_this_directory[album][0] = file
            else:
                print("Here is a file without album: {0}".format(filename))
        for name,album in albums_in_this_directory.items():
            print("\n**************************************************************************")
            print("I found an album '{0}' in directory '{1}' containing {2} files.".format(name,dirpath,len(album)))
            do_album(album)

if __name__=="__main__":
    walk(sys.argv[1])
