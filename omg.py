#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-
# Copyright 2009 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

import mpd
import db
import config
import os

MPD_HOST = "localhost"
MPD_PORT = "6600"
_mpdclient = mpd.MPDClient()
itags = {} # dict of indexed tags and their tagid
itags_reverse = {} # same in other direction (bäh)
def init():
    #_mpdclient.connect(host=MPD_HOST, port=MPD_PORT)
    
    db.connect()
    result = db.query("SELECT * FROM tagids;")
    for id,name in result:
-        itags[name] = id
    itags_reverse = {y:x for x,y in itags.items()} # <3 python :)
    
    
def close():
    _mpdclient.disconnect()

# -------- "file functions": Functions for operating with real files on the filesystem. -----------
def abs_path(file):
    """Returns the absolute path of a music file inside the collection directory."""
    return os.path.join(config.get("music","collection"),file)

def rel_path(file):
    """Returns the relative path of a music file against the collection base path."""
    return os.path.relpath(file,config.get("music","collection"))

def read_tags_from_file(file):
    """Returns the tags of a file as dictionary of strings as keys and lists of strings as values."""
    
    import subprocess
    if not os.path.isabs(file):
        file = abs_path(file)
    proc = subprocess.Popen([config.get("misc","printtags_cmd"),file], stdout=subprocess.PIPE)
    stdout = proc.communicate()[0].decode("utf-8")
    if proc.returncode > 0:
        print(file)
        print(stdout)
    tags = {}
    for line in stdout.splitlines():
        tag, value = line.split("=",1)
        if not tag in tags:
            tags[tag] = []
        tags[tag].append(value)
    return tags


def compute_hash(file):
    """Computes the hash of the audio stream of the given file."""
    
    import hashlib,tempfile,subprocess
    handle, tmpfile = tempfile.mkstemp()
    subprocess.check_call(
        ["mplayer", "-dumpfile", tmpfile, "-dumpaudio", abs_path(file)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    # wtf ? for some reason handle is int instead of file handle, as said in documentation
    handle = open(tmpfile,"br")
    hashcode = hashlib.sha1(handle.read()).hexdigest()
    handle.close()
    os.remove(tmpfile)
    return hashcode
# -------------------------------------------------------------------------------------------------



# ------------------- database management functions -----------------------------------------------

def id_from_filename(filename):
    """Tries to retrieve the ID from the file with the given path.
    
    May return None if the path is not present in the database. This function does NOT check
    for uniqueness of the path."""
    return db.query("SELECT id FROM files WHERE path='?';", filename).get_single()


def get_value_id(tag,value,insert=False):
    """Looks up the id of a tag value. If the value is not found and insert=True, create an entry,
    otherwise return None."""
    result = db.query("SELECT id FROM tag_{0} WHERE 'value'='?';".format(tag),value).get_single()
    if insert and not result:
        result = add_tag_value(tag,value)
    return result
    

def add_container(name,tags={},elements=0):
    db.query("INSERT INTO containers (name,elements) VALUES('?','?');", name,elements)
    newid = db.query('SELECT LAST_INSERT_ID();').get_single() # the new container's ID
    set_tags(cid, tags)


def add_tag(container_id, tagname=None, tagid=None, value=None, valueid=None):
    """Generic tag adding function. Either tagname or tagid and either value or valueid must be given."""
    
    if tagid:
        tagname=itags_reverse[tagid]
    if not tagname:
        raise ValueError("Either tagid or tagname must be set.")
    if tagname in itags: # yap, indexed tag
        if not valueid:
            if not value:
                raise ValueError("Either value or valueid must be set.")
            valueid=get_value_id(tagname,value,insert=True)
        db.query("INSERT INTO tags VALUES('?','?','?');", container_id, itags[tagname], valueid)
    else: # other tag
        if not value:
            raise ValueError("add_tag called for and unindexed tag, so value must be set.")
    db.query("INSERT INTO othertags VALUES('?','?','?');", container_id, tagname, value)        


def add_tag_value(tagname,value):
    """Adds a new value entry to an indexed tag. Returns the newly created ID."""
    
    db.query("INSERT INTO tag_{0} (value) VALUES('?');".format(tagname), value)
    return db.query('SELECT LAST_INSERT_ID();').get_single()
    
    
def set_tags(cid, tags, append=False):
    """Sets the tags of container with id <cid> to the supplied tags, which should be a dictionary.
    
    If the optional parameter append is set to True, existing tags won't be touched, instead the 
    given ones will be added. This function will not check for duplicates in that case."""
    
    existing_tags = db.query("SELECT * FROM tags WHERE 'container_id'='?';", cid)
    if len(existing_tags) > 0:
        print("Warning: Deleting existing tags from container {0}".format(cid))
    db.query("DELETE FROM tags WHERE 'container_id'='?';", cid)
    for tag in tags.keys():
        for value in tags[tag]:
            add_tag(container_id=cid,tagname=tag,value=value)

def add_file(path):
    """Adds a new file to the database.
    
    If path is a relative path, the music collection base path is added.
    Does  not check for uniqueness, so only call this when you need. Returns the new file's ID.
    Also adds all tags of the file to the database."""
    
    if not os.path.isabs(path):
        path = abs_path(path)
    db.query("INSERT INTO files (path,hash) VALUES('?','?');", rel_path(path),compute_hash(path))
    # read the files tags and add them to the database

    file_id = db.query('SELECT LAST_INSERT_ID();').get_single() #the new file's ID
    tags = read_tags_from_file(path)
    set_tags(file_id,tags)
    return file_id
    
def add_content(container_id, i, file_id):
    """Adds new content to a container in the database.
    
    The file with given file_id will be the i-th element of the container with container_id. May throw
    an exception if this container already has an element with the given file_id."""
    db.query('INSERT INTO contents VALUES(?,?,?);', container_id, i, file_id)

def add_file_container(name, files):
    """Adds a new file container to the database, whose contents are ordered as in files."""
    
    container_id = add_container(name)
    for index, file in enumerate(files,1):
        file_id = id_from_filename(file)
        if file_id == None:
            file_id = add_file(file)
        add_content(container_id, index, file_id)

# ---------- deprecated / temporary / debugging / omgwtf functions
def mpdClient(host=MPD_HOST, port=MPD_PORT):
    client = mpd.MPDClient()
    client.connect(host=host, port=port)
    return client