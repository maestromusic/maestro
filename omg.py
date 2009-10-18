#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-
# Copyright 2009 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

import db
import config
import os
import pickle
import datetime
import logging
import constants

class Container(dict):
    """Python representation of a Container, which is just a dictionary position->container that has an id, a name and tags."""
    def __init__(self,id=None,name=None,tags={}):
        dict.__init__(self)
        self.name=name
        self.id=id
        self.tags=tags

class File(Container):
    """A File is a special container that may have a length and a hash. If the read_file-Parameter is True, length,name,tags and hash will be read from the file."""
    def __init__(self,path,id=None,tags={},length=None,hash=None,read_file=False):
        Container.__init__(self,id,name=os.path.basename(path),tags=tags)
        self.length = length
        self.hash=hash
        self.path=path
        if read_file:
            t = read_tags_from_file(path)
            self.length = t.length
            self.tags = t #hm...
            self.hash = compute_hash(path)
            

itags = {} # dict of indexed tags and their tagid
itags_reverse = {} # same in other direction (bäh)
initialized = False
ignored_tags = None
tagtypes = None
logger = None


def init():
    global initialized, logger, ignored_tags, tagtypes
    if initialized:
        raise Exception("Already init'ed.")
    logging.basicConfig(level=constants.LOGLEVELS[config.get("misc","loglevel")], format='%(levelname)s: %(message)s')
    logger = logging.getLogger(name="omg")
    db.connect()
    db.check_tables(create_tables=True,insert_tagids=True)
    result = db.query("SELECT id,tagname FROM tagids;")
    for id,name in result:
        itags[name] = id
    itags_reverse = {y:x for x,y in itags.items()} # <3 python :)
    ignored_tags = config.get("tags","ignored_tags").split(",")
    tagtypes = db.tagtypes
    initialized = True
    logger.debug("omg module initialized")
    

# -------- "file functions": Functions for operating with real files on the filesystem. -----------
def abs_path(file):
    """Returns the absolute path of a music file inside the collection directory, if it is not absolute already."""
    
    if not os.path.isabs(file):
        return os.path.join(config.get("music","collection"),file)
    else:
        return file

def rel_path(file):
    """Returns the relative path of a music file against the collection base path."""
    
    return os.path.relpath(file,config.get("music","collection"))

def read_tags_from_file(file):
    """Returns the tags of a file as dictionary of strings as keys and lists of strings as values."""
    
    import subprocess
    if not os.path.isabs(file):
        file = abs_path(file)
    proc = subprocess.Popen([config.get("misc","printtags_cmd"),file], stdout=subprocess.PIPE)
    stdout = proc.communicate()[0]
    if proc.returncode > 0:
        raise RuntimeError("Error calling printtags on file '{0}': {1}".format(file,stdout))
    tags = pickle.loads(stdout)
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
    """Retrieves the container_id of a file from the given path, or None if it is not found."""
    return db.query("SELECT container_id FROM files WHERE path='?';", rel_path(filename)).get_single()

def id_from_hash(hash):
    """Retrieves the container_id of a file from its hash, or None if it is not found."""
    result =  db.query("SELECT container_id FROM files WHERE hash='?';", hash)
    if len(result)==1:
        return result.get_single()
    else:
        raise RuntimeError("Hash not unique upon filenames!")


def get_value_id(tag,value,insert=False):
    """Looks up the id of a tag value. If the value is not found and insert=True, create an entry,
    otherwise return None."""
    
    if db.tagtypes[tag]=="date": #translate date into a format that MySQL likes
        if len(value)==4: # only year is given
            value="{0}-00-00".format(value)
        elif len(value)==2: # year in 2-digit form
            if value[0]==0:
                value="20{0}-00-00".format(value)
            else:
                value="19{0}-00-00".format(value)

    result = db.query("SELECT id FROM tag_{0} WHERE value='?';".format(tag),value).get_single()
    if insert and not result:
        result = add_tag_value(tag,value)
    return result
    
def add_container(name,tags={},elements=0):
    """Adds a container to the database, which can have tags and a number of elements."""
    db.query("INSERT INTO containers (name,elements) VALUES('?','?');", name,elements)
    newid = db.query('SELECT LAST_INSERT_ID();').get_single() # the new container's ID
    set_tags(newid, tags)
    return newid


def add_tag(container_id, tagname=None, tagid=None, value=None, valueid=None):
    """Generic tag adding function. Either tagname or tagid and either value or valueid must be given."""
    
    if tagid:
        tagname=itags_reverse[tagid]
    if not tagname:
        raise ValueError("Either tagid or tagname must be set.")
    if tagname in ignored_tags:
        logger.debug("Ignored tag {0} from container_id {1}".format(tagname, container_id))
        return
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
    """Adds a new value entry to an indexed tag. Returns the newly created ID. Warning: Does NOT check for uniqueness."""
    
    db.query("INSERT INTO tag_{0} (value) VALUES('?');".format(tagname), value)
    return db.query('SELECT LAST_INSERT_ID();').get_single()
    
    
def set_tags(cid, tags, append=False):
    """Sets the tags of container with id <cid> to the supplied tags, which should be a dictionary.
    
    If the optional parameter append is set to True, existing tags won't be touched, instead the 
    given ones will be added. This function will not check for duplicates in that case."""
    
    existing_tags = db.query("SELECT * FROM tags WHERE 'container_id'='?';", cid)
    if len(existing_tags) > 0:
        logger.warning("Deleting existing indexed tags from container {0}".format(cid))
    db.query("DELETE FROM tags WHERE 'container_id'='?';", cid)
    existing_othertags = db.query("SELECT * FROM othertags WHERE 'container_id'='?';",cid)
    if len(existing_othertags) >0:
        logger.warning("Deleting existing othertags from container {0}".format(cid))
    db.query("DELETE FROM othertags WHERE 'container_id'='?';", cid)
    for tag in tags.keys():
        if tag in ignored_tags:
            continue
        for value in tags[tag]:
            add_tag(container_id=cid,tagname=tag,value=value)

def add_file(path=None, file=None):
    """Adds a new file to the database. The file can be given as path or as omg.File object. Returns the container_id.
    
    If path is a relative path, the music collection base path is added.
    Does  not check for uniqueness, so only call this when you need. Returns the new file's ID.
    Also adds all tags of the file to the database."""
    if not path==None:
        return add_file(path=None, file=File(path=path))
    if file==None:
        raise ValueError("Either path or file must not be None.")
    if not os.path.isabs(file.path):
        path = abs_path(file.path)
    else:
        path = file.path
    if not file.tags:
        tags = read_tags_from_file(path)
    else:
        tags = file.tags
    if not file.hash:
        hash = compute_hash(path)
    else:
        hash = file.hash
    file_id = add_container(name=os.path.basename(path),tags=tags,elements=0)
    # now take care of the files table
    db.query(
        "INSERT INTO files (container_id,path,hash,length) VALUES(?,'?','?',?);",
        file_id,
        rel_path(path),
        hash,
        int(tags.length))
    return file_id
    
def add_content(container_id, i, content_id):
    """Adds new content to a container in the database.
    
    The file with given file_id will be the i-th element of the container with container_id. May throw
    an exception if this container already has an element with the given file_id."""
    db.query('INSERT INTO contents VALUES(?,?,?);', container_id, i, content_id)

def add_file_container(name=None, contents=None, tags={}, container=None):
    """Adds a new container to the database whose contents are only files."""
    
    if not container==None:
        container_id = add_container(container.name, tags=container.tags, elements=len(container))
        for tracknumber in container:
            file_id = id_from_filename(container[tracknumber].path)
            if file_id == None:
                file_id = add_file(file=container[tracknumber])
            add_content(container_id, tracknumber, file_id)
    else: #deprecated
        container_id = add_container(name,tags=tags, elements=len(contents))
        for index, file in enumerate(contents,1):
            file_id = id_from_filename(file)
            if file_id == None:
                file_id = add_file(file=file)
            add_content(container_id, index, file_id)
    
def del_container(cid):
    """Removes a container together with all of its content and tag references from the database.
    
    If the content is a file, also deletes its entry from the files table."""
    
    db.query("DELETE FROM tags WHERE container_id='?';", cid) # delete tag references
    db.query("DELETE FROM othertags WHERE container_id='?';",cid) # delete othertag references
    db.query("DELETE FROM contents WHERE container_id='?' OR element_id='?';",cid,cid) # delete content relations
    db.query("DELETE FROM files WHERE container_id='?';",cid) # delete file entry, if present
    db.query("DELETE FROM containers WHERE id='?';",cid) # remove container itself

def del_file(path=None,hash=None,id=None):
    """Deletes a file from the database, either by path, hash or id."""
    
    if id:
        return del_container(id)
    elif path:
        return del_container(id_from_filename(path))
    elif hash:
        return del_container(id_from_hash(path))
    else:
        raise ValueError("One of the arguments must be set.")

# initialize module on loading
init()
