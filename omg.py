#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-

import mpd
import mysql
import config

MPD_HOST = "localhost"
MPD_PORT = "6600"
_mpdclient = mpd.MPDClient()
def init():
    #_mpdclient.connect(host=MPD_HOST, port=MPD_PORT)
    
    global _db
    _db = mysql.MySQL(
        config.get("database","mysql_user"),
        config.get("database","mysql_password"),
        config.get("database","mysql_db"),
        config.get("database","mysql_host")
        )
    
def close():
    _mpdclient.disconnect()

def add_container(name, tags="", description=""):
    _db.query("INSERT INTO containers (name,tags,description) VALUES('?','?','?');", name, tags,description)
    return _db.query('SELECT LAST_INSERT_ID();').get_single() # the new container's ID

def add_file(path):
    """Adds a new file to the database. Does  not check for uniqueness, so only call this when you need."""
    
    _db.query("INSERT INTO files (path) VALUES('?');", path)
    return _db.query('SELECT LAST_INSERT_ID();').get_single() #the new file's ID
    
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

def mpdClient(host=MPD_HOST, port=MPD_PORT):
    client = mpd.MPDClient()
    client.connect(host=host, port=port)
    return client