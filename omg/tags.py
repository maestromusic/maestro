#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

"""Module for tag handling.

This module provides methods to initialize the tag lists ased on the database, to convert tag-ids to tagnames and vice versa, etc.. Call updateIndexedTags at program start to initialize and use one of the following ways to get tags:

- The easiest way is the get-method which takes a tag-id or an tag-name as parameter.
- For some tags which have a special meaning to the program and cannot always be treated generically (e.g. the title-tag) where exist constants (e.g. TITLE). This allows to use tags.TITLE instead of tags.get(config.get("tags","title_tag")) as the user may decide to use another tagname than "title" for his titles.
- To iterate over all indexed tags use the list-method.
- You may create tags simply via the constructors of IndexedTag or OtherTag. But in case of indexed tags the get-method translates automatically from tag-ids to tagnames and vice versa and it doesn't create new instances and in the other case it does just the same job as the OtherTag-constructor, so it is usually better to use that method.
"""
from omg import config, database

# Module variables - Will be initialized with the first call of updateIndexedTags.
#=================================================================================
# Dictionaries of all indexed Tags. From outside the module use the get-method instead of these private variables.
_tagsById = None
_tagsByName = None

# List of all indexed tags in unspecified order. Use this to iterate over all indexed tags.
list = None

# Tags which have a special meaning for the application and cannot always be treated generically.
# Will be initialized with the first call of updateIndexedTags, so remember to change also that function whenever changing the following lines.
TITLE = None
ALBUM = None
ARTIST = None
COMPOSER = None
DATE = None

class Tag:
    """Baseclass for tags. Tags contain a tagname and compare equal if and only this tagname is equal. Tags may be used as dictionary keys."""
    def __init__(self,name):
        self.name = name
    
    def isIndexed(self):
        """Return whether this tag is indexed (i.e. of type IndexedTag)."""
        return isinstance(self,IndexedTag)
        
    def __eq__(self,other):
        return self.name == other.name
        
    def __ne__(self,other):
        return self.name != other.name

    def __hash__(self):
        return self.name.__hash__()

    def __repr__(self):
        return '"{0}"'.format(self.name)

    def __str__(self):
        return self.name
        
        
class IndexedTag(Tag):
    """Subclass for all indexed tags. These tags contain in addition to their name an id and compare equal if and only if this id is equal. In most cases you won't instantiate this class but use tags.get to get the already existing instances."""
    def __init__(self,id,name,type):
        self.id = id
        self.name = name
        self.type = type

    def __eq__(self,other):
        return self.id == other.id
    
    def __ne__(self,other):
        return self.id != other.id

    def __hash__(self):
        return self.id

    #TODO: The following comparison methods should not be used! Unfortunately PrettyPrinter sorts dictionary keys and raises exceptions if they cannot be sorted (confer issue 7429).
    def __ge__(self,other):
        return self.id >= other.id
        
    def __gt__(self,other):
        return self.id > other.id
        
    def __le__(self,other):
        return self.id <= other.id
    
    def __lt__(self,other):
        return self.id < other.id
        

class OtherTag(Tag):
    """Special class for tags which are not indexed."""
    pass


def get(identifier):
    """Return the tag identified by <identifier>. If <identifier> is an integer return the indexed tag with this id. If <identifier> is a string return the tag with this name (of type IndexedTag if there is an indexed tag of this name, otherwise OtherTag). In the case of indexed tags this method does not create new instances of the tags but returns always the same instance."""
    if isinstance(identifier,int):
        return _tagsById[identifier]
    elif isinstance(identifier,str):
        if identifier in _tagsByName:
            return _tagsByName[identifier]
        else: return OtherTag(identifier)
    else: raise Exception("Identifier's type is neither int nor string")


def updateIndexedTags():
    """Initialize (or update) the variables of this module based on the information of the tagids-table. At program start or after changes of that table this method must be called to ensure the module has the correct indexed tags and their IDs."""
    global _tagsById,_tagsByName,list
    _tagsById = {}
    _tagsByName = {}
    db = database.get()
    for row in db.query("SELECT id,tagname,tagtype FROM tagids"):
        newTag = IndexedTag(*row)
        _tagsById[row[0]] = newTag
        _tagsByName[row[1]] = newTag
    
    list = _tagsById.values()
    
    global TITLE,ARTIST,ALBUM,COMPOSER,PERFORMER,DATE
    TITLE = _tagsByName[config.get("tags","title_tag")]
    ARTIST = _tagsByName[config.get("tags","artist_tag")]
    ALBUM = _tagsByName[config.get("tags","album_tag")]
    COMPOSER = _tagsByName[config.get("tags","composer_tag")]
    PERFORMER = _tagsByName[config.get("tags","performer_tag")]
    DATE = _tagsByName[config.get("tags","date_tag")]