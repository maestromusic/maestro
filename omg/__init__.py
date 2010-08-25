#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-
# Copyright 2009 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from omg import realfiles, database, constants, config
import os
import pickle
import datetime
import logging

def initLogger():
    logging.basicConfig(level=constants.LOGLEVELS[config.get("misc","loglevel")], format='%(levelname)s: %(message)s')

def relPath(file):
    """Returns the relative path of a music file against the collection base path."""
    return os.path.relpath(file,config.get("music","collection"))

def absPath(file):
    """Returns the absolute path of a music file inside the collection directory, if it is not absolute already."""
    if not os.path.isabs(file):
        return os.path.join(config.get("music","collection"),file)
    else:
        return file
    
#class Container(dict):
#    """Python representation of a Container, which is just a dictionary position->container that has an id, a name and tags."""
#    def __init__(self,container_id=None,name=None,tags={}):
#        dict.__init__(self)
#        self.name=name
#        self.container_id=container_id
#        self.tags=tags
#    
#    def __str__(self):
#        ret = "({}: ".format(self.name)
#        for el in self.keys():
#            ret += "{0}:{1} ".format(el, self[el])
#        ret += ")"
#        return ret
#    
#    def _pprint(self,depth):
#        indent = "    "*depth
#        print(indent + self.name)
#        for el in sorted(self.keys()):
#            self[el]._pprint(depth+1)
#    
#    def pprint(self):
#        self._pprint(0)
#
#class File(Container):
#    """A File is a special container that may have a length and a hash. If the read_file-Parameter is True, length,name,tags and hash will be read from the file."""
#    def __init__(self,path,container_id=None,tags={},length=None,hash=None,read_file=False):
#        Container.__init__(self,container_id,name=os.path.basename(path),tags=tags)
#        self.length = length
#        self.hash=hash
#        self.path=path
#        if read_file:
#            self.read_tags_from_filesystem()
#            self.hash = compute_hash(path)
#    
#    def read_tags_from_filesystem(self):
#        real = realfiles.File(abs_path(self.path))
#        real.read()
#        self.tags = real.tags
#        self.length = real.length
#    
#    def write_tags_to_filesystem(self):
#        real = realfiles.File(abs_path(self.path))
#        real.tags = self.tags
#        real.save_tags()
#    
#    def _pprint(self,depth):
#        print("    "*depth + self.path)
#    
#    def __str__(self):
#        return self.path
#
#itags = {} # dict of indexed tags and their tagid
#itags_reverse = {} # same in other direction (bäh)
#initialized = False
#ignored_tags = None
#tagtypes = None
#logger = None
#db = None
#
#
#def init():
#    global initialized, logger, ignored_tags, tagtypes, db
#    if initialized:
#        raise Exception("Already init'ed.")
#    logger = logging.getLogger(name="omg")
#    database.connect()
#    db = database.db
#    if len(database.checkMissingTables()) > 0:
#        logger.warning("There are tables missing in the database, will create them.")
#        database.checkMissingTables(True)
#    result = db.query("SELECT id,tagname FROM tagids;")
#    for id,name in result:
#        itags[name] = id
#    itags_reverse = {y:x for x,y in itags.items()} # <3 python :)
#    ignored_tags = config.get("tags","ignored_tags").split(",")
#    tagtypes = database._parseIndexedTags()
#    initialized = True
#    logger.debug("omg module initialized")
#    
#
## -------- "file functions": Functions for operating with real files on the filesystem. -----------
#def abs_path(file):
#    """Returns the absolute path of a music file inside the collection directory, if it is not absolute already."""
#    
#    if not os.path.isabs(file):
#        return os.path.join(config.get("music","collection"),file)
#    else:
#        return file
#
#def rel_path(file):
#    """Returns the relative path of a music file against the collection base path."""
#    
#    return os.path.relpath(file,config.get("music","collection"))
#
#def read_tags_from_file(file):
#    """Returns the tags of a file as dictionary of strings as keys and lists of strings as values."""
#    
#    import subprocess
#    if not os.path.isabs(file):
#        file = abs_path(file)
#    proc = subprocess.Popen([config.get("misc","printtags_cmd"),file], stdout=subprocess.PIPE)
#    stdout = proc.communicate()[0]
#    if proc.returncode > 0:
#        raise RuntimeError("Error calling printtags on file '{0}': {1}".format(file,stdout))
#    tags = pickle.loads(stdout)
#    return tags
#
#
#def compute_hash(file):
#    """Computes the hash of the audio stream of the given file."""
#
#    import hashlib,tempfile,subprocess
#    handle, tmpfile = tempfile.mkstemp()
#    subprocess.check_call(
#        ["mplayer", "-dumpfile", tmpfile, "-dumpaudio", abs_path(file)],
#        stdout=subprocess.PIPE,
#        stderr=subprocess.PIPE)
#    # wtf ? for some reason handle is int instead of file handle, as said in documentation
#    handle = open(tmpfile,"br")
#    hashcode = hashlib.sha1(handle.read()).hexdigest()
#    handle.close()
#    os.remove(tmpfile)
#    return hashcode
## -------------------------------------------------------------------------------------------------
#
#
#

#def get_value_id(tag,value,insert=False):
#    """Looks up the id of a tag value. If the value is not found and insert=True, create an entry,
#    otherwise return None."""
#    
#    if tagtypes[tag]=="date": #translate date into a format that MySQL likes
#        if len(value)==4: # only year is given
#            value="{0}-00-00".format(value)
#        elif len(value)==2: # year in 2-digit form
#            if value[0]==0:
#                value="20{0}-00-00".format(value)
#            else:
#                value="19{0}-00-00".format(value)
#
#    result = database.db.query("SELECT id FROM tag_{0} WHERE value=?;".format(tag),value).getSingle()
#    if insert and not result:
#        result = add_tag_value(tag,value)
#    return result
#
#def get_tags(container_id):
#    """Returns all tags of the given container_id as a dict of lists."""
#    
#    tags = {}
#    for tag in itags:
#        result = database.db.query(
#            "SELECT value FROM tags INNER JOIN tag_{0} ON value_id=id AND tag_id=? WHERE container_id=?;".format(tag),itags[tag], container_id)
#        for x in result:
#            if not tag in tags:
#                tags[tag] = []
#            tags[tag].append(x[0])
#    result = database.db.query("SELECT tagname,value FROM othertags WHERE container_id=?;",container_id)
#    for tag,value in result:
#        if not tag in tags:
#            tags[tag] = []
#        tags[tag].append(value)
#    return tags
#            
#def path_by_id(container_id):
#    """Returns the path of a file (None if it doesn't exist)."""
#    return database.db.query("SELECT path FROM files WHERE container_id=?;",container_id).getSingle()
#    
#    
#def get_container_by_id(cid):
#    """Returns a Container/File class hierarchy representing the container of given ID."""
#    path = path_by_id(cid)
#    if path==None: # this is a non-file container
#        ret = Container(container_id=cid)
#        ret.name = database.db.query("SELECT name FROM containers WHERE id=?;",cid).getSingle()
#        ret.container_id = cid
#        ret.tags = get_tags(cid)
#        contents = database.db.query("SELECT position,element_id FROM contents WHERE container_id=?;",cid)
#        for pos,el in contents:
#            ret[pos] = get_container_by_id(el)
#    else:
#        ret = File(path,container_id=cid)
#        ret.tags = get_tags(cid)
#    return ret

