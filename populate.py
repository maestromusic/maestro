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
import realfiles
FIND_DISC_RE=r" ?[([]?(?:cd|disc|part|teil|disk) ?([iI1-9]+)[)\]]?"

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
            elif 'artist' in same_tags: #composer not in same_tags
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
    discnumber = None
    write_discnumber_to_tags = False
    meta_container = None
    while not accepted:
        result = db.query("SELECT id FROM containers WHERE name='?';", album.name)
        if len(result) == 1:
            album.container_id = result[0][0]
        print("+++++ I SUGGEST: +++++")
        #-------- 1.: Name of the container ----------------------------------
        print("1]  Name of the Container: {0}".format(album.name))
        if (album.container_id!=None):
            print("     [EXISTS WITH ID: {0}]".format(album.container_id))
        
        #-------- 2.: Contents -----------------------------------------------
        print("2]  Contents:")
        for track in sorted(album.keys()):
            print("      {0}".format(os.path.basename(album[track].path)))
        
        #-------- 3.: Tags of the container (common tags) --------------------
        print("3]  Tags (common to all files):")
        for tag in album.tags:
            for v in album.tags[tag]:
                print("    {0}={1}".format(tag,v))
        
        #-------- 4.: Different tags -----------------------------------------
        if len(different_tags) > 0:
            print("4]  !!TAKE CARE: Tags which are NOT equal on all songs!!:")
            for tag in different_tags:
                print("    {0}".format(tag))
        
        #-------- 5.: Extra tags ---------------------------------------------
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
        
        #-------- 6.: Multi-Disc Container Identification -------------------

        if "discnumber" in album.tags:
            discnumber = int(album.tags["discnumber"][0])
        discstring = re.findall(FIND_DISC_RE,album.tags["album"][0],flags=re.IGNORECASE)
        if len(discstring) > 0 and discnumber==None:
            discnumber = discstring[0]
            if discnumber.lower().startswith("i"): #roman number, support I-III :)
                discnumber = len(discnumber)
            write_discnumber_to_tags = True
        if discnumber!= None:
            album.tags["discnumber"] = [ discnumber ]
            print("6]  Part of Multi-Disc container:")
            discname_reduced = re.sub(FIND_DISC_RE,"",album.name,flags=re.IGNORECASE)
            result = db.query("SELECT id FROM containers WHERE name='?';", discname_reduced)
            if len(result)==0:
                meta_container = discname_reduced
            elif len(result)==1:
                meta_container = int(result[0][0])
            else:
                print("Sorry, you already have more than one container named '{0}', you have to do this by hand.".format(discname_reduced))
            print("    This is disc number {0} of container '{1}'".format(discnumber, discname_reduced))
            if write_discnumber_to_tags:
                print("      [write the discnumber to the files]")
            if isinstance(meta_container,str):
                print("      [create meta container]")
            elif isinstance(meta_container,int):
                print("      [exists with id {0}]".format(meta_container))
        
        
        ans = input("What do ou want me to do? Accept [Enter] or further examine a section [1-6], [e] to run exfalso, [s] to skip?")
        if ans=="1":
            album.name = input("Enter new name:\n")
        elif ans in ["e","E"]:
            subprocess.call(["exfalso", os.path.split(list(album.values())[0].path)[0]])
            for file in album.values():
                realfile = realfiles.File(os.path.abspath(file.path))
                realfile.read()
                file.tags = realfile.tags
            different_tags = guess_album(album)
        elif ans in ["s","S"]:
            return
        elif ans=="":
            accepted = True
    print("you have accepted. I will now do some SQL magic")
    album_id = omg.add_file_container(container=album)
    
    if write_discnumber_to_tags:
        for file in album.values():
            file.tags["discnumber"] = [ discnumber ]
            file.write_tags_to_filesystem()
            logger.info("discnumber tag added to file {0}".format(file.path))
    if discnumber != None:
        if isinstance(meta_container,str):
            meta_container_id = omg.add_container(name=meta_container)
        elif isinstance(meta_container,int):
            meta_container_id = meta_container
        else:
            print("Sorry, you already have more than one meta container of the desired name, you have to do this by hand.")
        if meta_container_id != None:
            omg.add_content(meta_container_id, discnumber, album_id)
    


def find_new_albums(path):
    """Generator function which tries to find albums in the filesystem tree.
    
    Yields an omg.Container without any tags. The tags and the name for the album should be examined by another function."""
    for dirpath, dirnames, filenames in os.walk(path):
        albums_in_this_directory = {}
        ignored_albums=[]
        for filename in (os.path.normpath(os.path.abspath(os.path.join(dirpath, f))) for f in filenames):
            if omg.id_from_filename(filename):
                logger.debug("Skipping file '{0}' which is already in the database.".format(filename))
                continue
            try:
                realfile = realfiles.File(os.path.abspath(filename))
                realfile.read()
            except realfiles.NoTagError:
                logger.warning("Skipping file '{0}' which has no tag".format(filename))
                continue
            t = realfile.tags
            if "album" in t:
                album = t["album"][0]
                if album in ignored_albums:
                    continue
                file = omg.File(filename, tags=t, length=realfile.length)
                if not album in albums_in_this_directory:
                    albums_in_this_directory[album] = omg.Container()
                if "tracknumber" in t:
                    trkn = int(t["tracknumber"][0].split("/")[0]) # support 02/15 style
                    albums_in_this_directory[album][trkn] = file
                else: # file without tracknumber, bah
                    if 0 in albums_in_this_directory[album]:
                        print("More than one file in this album without tracknumber, don't know what to do: \n{0}".format(filename))
                        del albums_in_this_directory[album]
                        ignored_albums.append(album)
                    else:
                        albums_in_this_directory[album][0] = file
            else:
                print("Here is a file without album, I'll skip this: {0}".format(filename))
        for name,album in albums_in_this_directory.items():
            print("\n**************************************************************************")
            print("I found an album '{0}' in directory '{1}' containing {2} files.".format(name,dirpath,len(album)))
            yield album

