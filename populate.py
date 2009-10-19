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
import re
import db
import constants
import subprocess
import logging


logger = logging.getLogger(name="populate")

def guess_album(album):
    """Try to guess name and tags of an album. Modifies the argument; in addition, returns a set of tags which are present in all files but different."""
    
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
    album.tags = { tag:common_tag_values[tag] for tag in same_tags }
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
    return different_tags

def do_album(album):
    """Processes an album, which should be of type omg.Container."""
    
    different_tags = guess_album(album)
    
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
            extratags = set(album[track].tags.keys()) - set(album.tags.keys()) - set(["tracknumber","title"]) - different_tags
            if len(extratags) > 0:
                if not have_extratags:
                    print("5] !!TAKE CARE!!: We have some extra tags in some files:")
                    have_extratags = True
                print("The file '{0}' has extra tags:".format(album[track].path))
                for tag in extratags:
                    print("  {0}={1}".format(tag,album[track].tags[tag]))
        ans = input("What do you want me to do? Accept [Enter] or further examine a section [1-6]?")
        if ans=="1":
            album.name = input("Enter new name:\n")
        elif ans=="E":
            subprocess.call(["exfalso", os.path.split(list(album.values())[0].path)[0]])
            for file in album.values():
                file.tags = omg.read_tags_from_file(file.path)
            different_tags = guess_album(album)
        elif ans=="":
            accepted = True
    print("you have accepted. I will now do some SQL magic")
    album_id = omg.add_file_container(container=album)
    
    # find out if this is part of a multi-disc collection
    discnumber = None
    if "discnumber" in album.tags:
        discnumber = int(album.tags["discnumber"][0])
    discstring = re.findall(r" ?[([](?:cd|disc) ?([1-9])[)\]]$",album.name,flags=re.IGNORECASE)
    if len(discstring) > 0 and discnumber==None:
        discnumber = discstring[0]
        print("This looks like a part of a multi-disc container; I found a discnumber {0}".format(discnumber))
        ans = input("Add this to the album tags? [Yn]")
        if ans in constants.YES_ANSWERS:
            album.tags["discnumber"] = [ discnumber ]
            print("Added 'discnumber={0}' to the album tags".format(discnumber))
    if discnumber != None:
        discname_reduced = re.sub(r" ?[([](?:cd|disc) ?([1-9])[)\]]$","",album.name,flags=re.IGNORECASE)
        result = db.query("SELECT id FROM containers WHERE name='?';", discname_reduced)
        container_id = None
        if len(result)==0:
            ans = input("Create a new Container '{0}'? [Yn]".format(discname_reduced))
            if ans in constants.YES_ANSWERS:
                container_id = omg.add_container(name=discname_reduced)
        elif len(result)==1:
            container_id = result[0][0]
        else:
            print("Sorry, you already have more than one container named '{0}', you have to do this by hand.".format(discname_reduced))
        if container_id != None:
            ans = input("Add album '{0}' as element number {1} to container '{2}'? [Yn]".format(album.tags["album"][0], discnumber, discname_reduced))
            if ans in constants.YES_ANSWERS:
                omg.add_content(container_id, discnumber, album_id)
    


def walk(path):
    for dirpath, dirnames, filenames in os.walk(path):
        albums_in_this_directory = {}
        for filename in [os.path.join(dirpath, f) for f in filenames]:
            if omg.id_from_filename(filename):
                logger.debug("Skipping file '{0}' which is already in the database.".format(filename))
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
