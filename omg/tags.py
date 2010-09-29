#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

"""Module for tag handling.

This module provides methods to initialize the tag lists based on the database, to convert tag-ids to tagnames and vice versa, to store tags, etc.. Call init at program start to initialize and use one of the following ways to get tags:

- The easiest way is the get-method which takes a tag-id or an tag-name as parameter.
- For some tags which have a special meaning to the program and cannot always be treated generically (e.g. the title-tag) where exist constants (e.g. TITLE). This allows to use tags.TITLE instead of tags.get(config.options.tags.title_tag) as the user may decide to use another tagname than "title" for his titles.
- To iterate over all indexed tags use tagList.
- You may create tags simply via the constructors of IndexedTag or OtherTag. But in case of indexed tags the get-method translates automatically from tag-ids to tag-names and vice versa and it doesn't create new instances and in the other case it does just the same job as the OtherTag-constructor, so you are usually better off using that method.
"""
from collections import Sequence
from omg import constants, database, FlexiDate
from omg.config import options
import logging, datetime

logger = logging.getLogger("tags")

# Module variables - Will be initialized with the first call of init.
#=================================================================================
# Dictionaries of all indexed tags. From outside the module use the get-method instead of these private variables.
_tagsById = None
_tagsByName = None

# list of all tags that are ignored by config file
_ignored = None

# List of all indexed tags in the order specified by the config-variable tags->tag_order (tags which are not contained in that list will appear in arbitrary order at the end of tagList). Us this to iterate over all tags.
tagList = None

# Tags which have a special meaning for the application and cannot always be treated generically.
# Will be initialized with the first call of init, so remember to change also that function whenever changing the following lines.
TITLE = None
ALBUM = None
DATE = None

TOTALLY_IGNORED_TAGS = ("tracknumber", "discnumber")

class Tag:
    """Baseclass for tags.
    
    Tags contain a tagname and compare equal if and only this tagname is equal. Tags may be used as dictionary keys. The only public attribute is name.
    """
    def __init__(self):
        raise RuntimeError("Cannot instantiate abstract base class Tag.")
    
    def isIndexed(self):
        """Return whether this tag is indexed (i.e. of type IndexedTag)."""
        return isinstance(self,IndexedTag)
    
    def isIgnored(self):
        """Return if the tag is ignored."""
        return self.name in TOTALLY_IGNORED_TAGS or self.name in _ignored
    
    def isValid(self,value):
        """Return whether the given value is could be a tag-value for this tag."""
        return True
        
    def __eq__(self,other):
        return self.name == other.name
        
    def __ne__(self,other):
        return self.name != other.name

    def __hash__(self):
        return self.name.__hash__()

    def __repr__(self):
        return '"{0}"'.format(self.name)

    def __str__(self):
        return self.translated()
        
    def translated(self):
        """Return the translation of this tag in the user's language. In most cases you will want to display this string rather than tag.name."""
        # TODO: Store the translations somewhere else
        nameDict = {
            'title': "Titel",
            'artist': "Künstler",
            'composer': "Komponist",
            'performer': "Performer",
            'conductor': "Dirigent",
            'album': "Album",
            'genre': "Genre",
            'date': "Datum",
            'description': "Beschreibung"
        }
        return nameDict.get(self.name,self.name) # if self.name is not contained in the dict return the name itself
        
        
class IndexedTag(Tag):
    """Subclass for all indexed tags.
    
    Indexed tags contain in addition to their name an id and compare equal if and only if this id is equal. In most cases you won't instantiate this class but use tags.get to get the already existing instances. Indexed tags have three public attributes: id, name and type where type must be one of the keys in database.tables.TagTable._tagQueries.
    """
    def __init__(self,id,name,type):
        self.id = id
        self.name = name
        self.type = type
    
    def getValue(self,valueId):
        """Retrieve the value of this tag with the given <valueId> from the corresponding tag-table."""
        tableName = "tag_"+self.name
        
        if self.type == 'date':
            value = FlexiDate.strptime(database.get().query(
                    "SELECT DATE_FORMAT(value, '%Y-%m-%d') FROM " + tableName + " WHERE id = ?", valueId
                ).getSingle())
        else:
            value = database.get().query("SELECT value FROM "+tableName+" WHERE id = ?",valueId).getSingle()
        return value
    
    def getValueId(self, value, insert=True):
        """Retrieve the id of the value of this tag with the given <value> name."""
        
        db = database.get()
        tableName = "tag_" + self.name
        if self.type == "date":
            value = value.SQLformat()
        valueId = db.query("SELECT id FROM " + tableName + " WHERE value = ?", value).getSingle()
        if insert and not valueId:
            valueId = db.query("INSERT INTO tag_{0} (value) VALUES(?);".format(self.name), value).insertId()
            logger.debug("creating new value {} for tag {}".format(value,self.name))
        return valueId
    
    def isValid(self,value):
        if self.type == 'varchar':
            return isinstance(value,str) and len(value) <= constants.TAG_VARCHAR_LENGTH
        elif self.type == 'text':
            return isinstance(value,str)
        elif self.type == 'date':
            if isinstance(value,FlexiDate):
                return True
            else:
                try: 
                    FlexiDate.strptime(value)
                except TypeError:
                    return False
                except ValueError:
                    return False
                else: return True
        else: assert False # should never happen
        
    def __eq__(self,other):
        return isinstance(other, IndexedTag) and self.id == other.id
    
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
    def __init__(self, name):
        if not name.isalnum():
            raise ValueError("Tag name must be alpha-numeric and contain at least one character.")
        self.name = name


def get(identifier):
    """Return the tag identified by <identifier>. If <identifier> is an integer return the tag with this id. If <identifier> is a string return the tag with this name. This method does not create new instances of the tags but returns always the same instance."""
    if isinstance(identifier,int):
        return _tagsById[identifier]
    elif isinstance(identifier,str):
        identifier = identifier.lower()
        if identifier in _tagsByName:
            return _tagsByName[identifier]
        else: return OtherTag(identifier)
    elif isinstance(identifier, Tag):
        return identifier
    else: raise RuntimeError("Identifier's type is neither int nor string: {} of type {}".format(identifier,type(identifier)))
    
def fromTranslation(translation):
    """Return the tag whose translation is <translation>. If no such tag exists, invoke get to return a tag. Use this method to get a tag from user input, especially when using combo-boxes with predefined values containing translated tags."""
    translation = translation.lower()
    for tag in tagList:
        if translation == tag.translated().lower():
            return tag
    return get(translation)

def parse(string,sep=','):
    """Parse a string containing tag-names (by default comma-separated, but you may specify a different separator) and return a list of corresponding tags. If <string> contains a substring that is not a tag name, it is simply ignored."""
    return [_tagsByName[name] for name in string.split(sep) if name in _tagsByName]

def addIndexedTag(identifier, type):
    if identifier in _tagsByName.keys():
        raise RuntimeError("requested creation of tag {} which is already there".format(identifier))
    from omg.database import tables
    db = database.get()
    tagtab = tables.TagTable(identifier, type)
    tagtab.create()
    id = db.query("INSERT INTO tagids (tagname,tagtype) VALUES (?,?)",identifier, type).insertId()
    init()
    return get(id)

def init():
    """Initialize the variables of this module based on the information of the tagids-table and config-file. At program start or after changes of that table this method must be called to ensure the module has the correct tags and their IDs."""
    global _tagsById,_tagsByName,tagList, _ignored
    _tagsById = {}
    _tagsByName = {}
    db = database.get()
    for row in db.query("SELECT id,tagname,tagtype FROM tagids"):
        newTag = IndexedTag(*row)
        _tagsById[row[0]] = newTag
        _tagsByName[row[1]] = newTag
    
    # tagList contains the tags in the order specified by tags->tag_order...
    tagList = [ _tagsByName[name] for name in options.tags.tag_order if name in _tagsByName ]
    # ...and then all remaining tags in arbitrary order
    tagList.extend(set(_tagsByName.values()) - set(tagList))
    
    _ignored = options.tags.ignored_tags
    global TITLE,ALBUM,DATE
    TITLE = _tagsByName[options.tags.title_tag]
    ALBUM = _tagsByName[options.tags.album_tag]
    DATE = _tagsByName[options.tags.date_tag]


class TagValueList(list):
    """List to store tags in a Storage-object. The only difference to a usual python list is that a TagValueList stores a reference to the Storage-object and will notify the storage if the list is empty. The storage will then remove the list."""
    def __init__(self,storage,aList=None):
        list.__init__(self,aList if aList is not None else [])
        self.storage = storage
    
    def __setitem__(self,key):
        list.__setitem__(self,key)
        
    def __delitem__(self,key):
        list.__delitem__(self,key)
        if len(self) == 0:
            self.storage._removeList(self)


class Storage(dict):
    """"Dictionary subclass used to store tags. As an element may have several values for the same tag, Storage maps tags to lists of tag-values. The class ensures that an instance never contains an empty list and adds a few useful functions to deal with such datastructures."""
    def __init__(self,*args):
        dict.__init__(self,*args)
    
    def copy(self):
        """Return a copy of this storage-object containing copies of the original tag-value-lists."""
        return Storage({tag: list(l) for tag,l in self.items()})
        
    def __setitem__(self,key,value):
        assert isinstance(value,Sequence) and not isinstance(value,str)
        if len(value) == 0:
            if key in self:
                del self[key]
            else: pass # I won't save an empty list
        else: dict.__setitem__(self,key,TagValueList(self,value))
    
    def _removeList(self,list):
        for key,value in self.items():
            if value == list:
                del self[key]
                return
                
    def add(self,tag,*values):
        """Add one or more values to the list of the given tag."""
        if not isinstance(tag,Tag):
            tag = get(tag)
        if tag not in self:
            self[tag] = values
        else: self[tag].extend(values)

    def addUnique(self,tag,*values):
        """Add one or more values to the list of the given tag. If a value is already contained in the list, do not add it again."""
        if not isinstance(tag,Tag):
            tag = get(tag)
        if tag not in self:
            # Values may contain repetitions, so we need to filter them away. Remember that self[tag] = [] won't work
            newList = []
            for value in values:
                if value not in newList:
                    newList.append(value)
            self[tag] = newList
        else:
            for value in values:
                if value not in self[tag]:
                    self[tag].append(value)
                
    def removeValues(self,tag,*values):
        """Remove one or more values from the list of the given tag. If a value is not contained in this Storage just skip it."""
        if not isinstance(tag,Tag):
            tag = get(tag)
        for value in values:
            try:
                self[tag].remove(value)
            except ValueError: pass 
        if not self[tag]:
            del self[tag]
            
    def merge(self,other):
        """Add all tags from <other> to this Storage. <other> may be another Storage-instance or a dict mapping tags to value-lists. Do not add already existing values again."""
        for tag,valueList in other.items():
            self.addUnique(tag,*valueList)
                
    def removeTags(self,other):
        """Remove all values from <other> from this Storage. <other> may be another Storage-instance or a dict mapping tags to value-lists. If <other> contains tags and values which are not contained in this Storage, just skip them."""
        for tag,valueList in other.items():
            self.removeValues(tag,*valueList)