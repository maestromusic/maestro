#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-
# Copyright 2009 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

import mpd
import mysql
import config
import os

MPD_HOST = "localhost"
MPD_PORT = "6600"
_mpdclient = mpd.MPDClient()
itags = {} # dict of indexed tags and their tagid
def init():
    #_mpdclient.connect(host=MPD_HOST, port=MPD_PORT)
    
    global _db
    _db = mysql.MySQL(
        config.get("database","mysql_user"),
        config.get("database","mysql_password"),
        config.get("database","mysql_db"),
        config.get("database","mysql_host")
        )
    result = _db.query("SELECT * FROM tagids;")
    for id,name in result:
        itags[name] = id
    
    
def close():
    _mpdclient.disconnect()

# -------- "file functions": Functions for operating with real files on the filesystem. -----------
def abs_path(file):
    """Returns the absolute path of a music file inside the collection directory."""
    return os.path.join(config.get("music","collection"),file)


def read_tags_from_file(file):
    """Returns the tags of a file as dictionary of strings as keys and lists of strings as values."""
    
    import subprocess
    proc = subprocess.Popen([config.get("misc","printtags_cmd"),abs_path(file)],stdout=subprocess.PIPE)
    stdout = proc.communicate()[0]
    tags = {}
    for line in [l.decode("utf-8") for l in stdout.splitlines()]:
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
def add_container(name, tags={}, description=""):
    _db.query("INSERT INTO containers (name,tags,description) VALUES('?','?','?');", name, tags,description)
    return _db.query('SELECT LAST_INSERT_ID();').get_single() # the new container's ID

def add_file(path):
    """Adds a new file to the database.
    
    Does  not check for uniqueness, so only call this when you need. Returns the new file's ID.
    Also adds all tags of the file to the database."""

    _db.query("INSERT INTO files (path,hash) VALUES('?','?');", path,compute_hash(path))
    # read the files tags and add them to the database

    file_id = _db.query('SELECT LAST_INSERT_ID();').get_single() #the new file's ID
    tags = read_tags_from_file(path)
    add_tags(file_id,tags)
    return theid
    
def add_content(container_id, i, file_id):
    """Adds new content to a container in the database.
    
    The file with given file_id will be the i-th element of the container with container_id. May throw
    an exception if this container already has an element with the given file_id."""
    _db.query('INSERT INTO contents VALUES(?,?,?);', container_id, i, file_id)

def id_from_filename(filename):
    """Tries to retrieve the ID from the file with the given path.
    
    May return None if the path is not present in the database. This function does NOT check
    for uniqueness of the path."""
    return _db.query("SELECT id FROM files WHERE path='?';", filename).get_single()

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