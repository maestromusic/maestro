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
- For some tags which have a special meaning to the program and cannot always be treated generically (e.g. the title-tag) where exist constants (e.g. TITLE). This allows to use tags.TITLE instead of tags.get(options.tags.title_tag) as the user may decide to use another tagname than "title" for his titles.
- To iterate over all indexed tags use tagList.
- You may create tags simply via the constructors of IndexedTag or OtherTag. But in case of indexed tags the get-method translates automatically from tag-ids to tag-names and vice versa and it doesn't create new instances and in the other case it does just the same job as the OtherTag-constructor, so you are usually better off using that method.
"""
import os.path, logging, datetime, xml.sax
from collections import Sequence
from xml.sax.handler import ContentHandler

from omg import constants, FlexiDate, getIcon
from omg.config import options

logger = logging.getLogger("tags")

# Module variables - Will be initialized with the first call of init.
#=================================================================================
# Dictionaries of all indexed tags. From outside the module use the get-method instead of these private variables.
_tagsById = None
_tagsByName = None

# list of all tags that are ignored by config file
_ignored = None

# Dict mapping keys to their translations
_translation = None

# Local reference to the database, will be created in init
db = None

# List of all indexed tags in the order specified by the config-variable tags->tag_order (tags which are not contained in that list will appear in arbitrary order at the end of tagList). Us this to iterate over all tags.
tagList = None

# Tags which have a special meaning for the application and cannot always be treated generically.
# Will be initialized with the first call of init, so remember to change also that function whenever changing the following lines.
TITLE = None
ALBUM = None
DATE = None

TOTALLY_IGNORED_TAGS = ("tracknumber", "discnumber")

class ValueType:
    """Class for the type of tag-values. Currently only three types are possible: varchar, date and text. For each of them there is an instance (e.g. tags.TYPE_VARCHAR) and you can get all of them via tags.TYPES. You should never create your own instances."""
    def __init__(self,name):
        """Create a new ValueType-instance with given name. Do NOT create your own instances, but use the instances created in this module."""
        self.name = name

    def __eq__(self,other):
        return isinstance(other,ValueType) and self.name == other.name

    def __ne__(self,other):
        return not isinstance(other,ValueType) or self.name != other.name
        
    def __hash__(self):
        return hash(self.name)
        
    def isValid(self,value):
        """Return whether the given value is a valid tag-value for tags of this type."""
        if self.name == 'varchar':
            return isinstance(value,str) and 0 < len(value.encode()) <= constants.TAG_VARCHAR_LENGTH
        elif self.name == 'text':
            return isinstance(value,str) and len(value) > 0
        elif self.name == 'date':
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

    def convertValue(self,newType,value):
        """Convert <value> from this type to <newType> and return the result. This method converts from FlexiDate (type date) to strings (types varchar and text) and vice versa. If conversion fails or the converted value is not valid for newType (confer ValueType.isValid), this method will raise a ValueError."""
        if self == TYPE_DATE and newType != TYPE_DATE:
            convertedValue = value.strftime()
        elif self != TYPE_DATE and newType == TYPE_DATE:
            convertedValue = FlexiDate.strptime(value)
        else: convertedValue = value # nothing to convert
        if newType.isValid(convertedValue):
            return convertedValue
        else: raise ValueError("Converted value {} is not valid for type {}.".format(convertedValue,newType))

    def sqlFormat(self,value):
        """Convert <value> into a string that can be inserted into database queries."""
        if self.name == 'date':
            if isinstance(value,FlexiDate):
                return value.sqlFormat()
            else: return FlexiDate.strptime(value).sqlFormat()
        else: return value

    @staticmethod
    def byName(name):
        """Given a type-name return the corresponding instance of this class."""
        for type in TYPES:
            if type.name == name:
                return type
        else: raise IndexError("There is no tag-type with name '{}'.".format(name))

    def valueFromString(self,string):
        """Convert a string (which must be valid for this tag-type) into the preferred representation of values of this type. Actually this method does nothing than convert strings to FlexiDates if this is the date-type."""
        if self == TYPE_DATE:
            return FlexiDate.strptime(string)
        else: return string

TYPE_VARCHAR = ValueType('varchar')
TYPE_TEXT = ValueType('text')
TYPE_DATE = ValueType('date')
TYPES = [TYPE_VARCHAR,TYPE_TEXT,TYPE_DATE]


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
        return other is not None and self.name == other.name
        
    def __ne__(self,other):
        return other is None or self.name != other.name

    def __hash__(self):
        return self.name.__hash__()

    def __repr__(self):
        return '"{0}"'.format(self.name)

    def __str__(self):
        return self.translated()
        
    def translated(self):
        """Return the translation of this tag in the user's language. In most cases you will want to display this string rather than tag.name."""
        return _translation.get(self.name,self.name) # if self.name is not contained in the dict return the name itself
    
    def iconPath(self):
        """Return the path to the icon of this tag or None if there is no such icon."""
        path = getIcon("tag_{}.png".format(self.name))
        return path if os.path.isfile(path) else None


class IndexedTag(Tag):
    """Subclass for all indexed tags.
    
    Indexed tags contain in addition to their name an id and compare equal if and only if this id is equal. In most cases you won't instantiate this class but use tags.get to get the already existing instances. Indexed tags have three public attributes: id, name and type where type must be one of the keys in database.tables.TagTable._tagQueries.
    """
    def __init__(self,id,name,type):
        assert isinstance(id,int) and isinstance(name,str) and isinstance(type,ValueType)
        self.id = id
        self.name = name.lower()
        self.type = type
    
    def isValid(self,value):
        """Return whether the given value is a valid tag-value for this tag (this depends only on the tag-type)."""
        return self.type.isValid(value)
        
    def sqlFormat(self,value):
        return self.type.sqlFormat(value)
        
    def __eq__(self,other):
        return other is not None and isinstance(other, IndexedTag) and self.id == other.id
    
    def __ne__(self,other):
        return other is None or not isinstance(other,IndexedTag) or self.id != other.id

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
        if len(name) == 0 or not name.isprintable():
            raise ValueError("Tag name must contain only printable characters and at least one of them: '{}'".format(name))
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
    else: raise RuntimeError("Identifier's type is neither int nor string nor tag: {} of type {}".format(identifier,type(identifier)))
    
def fromTranslation(translation):
    """Return the tag whose translation is <translation> (comparison is case-insensitive!). If no such tag exists, invoke get to return a tag. Use this method to get a tag from user input, especially when using combo-boxes with predefined values containing translated tags."""
    translation = translation.lower()
    for key,name in _translation:
        if name.lower() == translation:
            return get(key)
    else: return get(translation)

def parse(string,sep=','):
    """Parse a string containing tag-names (by default comma-separated, but you may specify a different separator) and return a list of corresponding tags. If <string> contains a substring that is not a tag name, it is simply ignored."""
    return [_tagsByName[name] for name in string.split(sep) if name in _tagsByName]

def addIndexedTag(name, type):
    if name in _tagsByName:
        raise RuntimeError("requested creation of tag {} which is already there".format(name))
    from omg import database
    from omg.database import tables
    tagtab = tables.TagTable(name,type)
    tagtab.create()
    id = database.get().query("INSERT INTO tagids (tagname,tagtype) VALUES (?,?)",name,type.name).insertId()
    newTag = IndexedTag(id,name,type)
    _tagsByName[name] = newTag
    _tagsById[id] = newTag
    tagList.append(newTag)
    #TODO: Popularize the new tag
    return newTag

def init():
    """Initialize the variables of this module based on the information of the tagids-table and config-file. At program start or after changes of that table this method must be called to ensure the module has the correct tags and their IDs."""
    global _tagsById,_tagsByName,tagList, _ignored, _translation

    # Initialize _tagsById, _tagsByName and tagList from the database
    from omg import database
    _tagsById = {}
    _tagsByName = {}
    for row in database.get().query("SELECT id,tagname,tagtype FROM tagids"):
        newTag = IndexedTag(row[0],row[1],ValueType.byName(row[2]))
        _tagsById[newTag.id] = newTag
        _tagsByName[newTag.name] = newTag
    
    # tagList contains the tags in the order specified by tags->tag_order...
    tagList = [ _tagsByName[name] for name in options.tags.tag_order if name in _tagsByName ]
    # ...and then all remaining tags in arbitrary order
    tagList.extend(set(_tagsByName.values()) - set(tagList))

    # Initialize _translation
    _translation = {}
    files = [os.path.join('i18n','tags.'+options.i18n.locale+'.xml'),
             os.path.join('i18n','tags.'+options.i18n.locale[:2]+'.xml')] #try de instead of de_DE
    if all(not os.path.exists(file) for file in files):
        logger.warning("I could not find a tag translation file for locale '{}'.".format(options.i18n.locale))
    else:
        for file in files:
            if os.path.exists(file):
                try:
                    xml.sax.parse(file,TranslationFileHandler())
                except xml.sax.SAXParseException as e:
                    logger.warning("I could not parse tag translation file '{}'. Error message: {}"
                                        .format(file,e.message()))
            
    _ignored = options.tags.ignored_tags
    
    global TITLE,ALBUM,DATE
    TITLE = _tagsByName[options.tags.title_tag]
    ALBUM = _tagsByName[options.tags.album_tag]
    DATE = _tagsByName[options.tags.date_tag]


def parseTagConfiguration(config):
    """Parse a string to configure tags and their types. This string should contain a comma-separated list of strings of the form tagname(tagtype) where the part in brackets is optional and defaults to 'varchar'. Check whether the syntax is correct and return a dictionary {tagname : tagtype}. Otherwise raise an exception."""
    import re
    # Matches strings like "   tagname (   tagtype   )   " (the part in brackets is optional) and stores the interesting parts in the first and third group.
    prog = re.compile('\s*(\w+)\s*(\(\s*(\w*)\s*\))?\s*$')
    tags = {}
    for tagstring in config.split(","):
        result = prog.match(tagstring)
        if result is None:
            raise Exception("Invalid syntax in the tag configuration ('{0}').".format(tagstring))
        tagname = result.groups()[0]
        tagtype = result.groups()[2]
        if not tagtype:
            tagtype = "varchar"
        if ValueType.byName(tagtype) is None:
            raise Exception("Unknown tag type: '{}'".format(tagtype))
        tags[tagname] = tagtype
    return tags


class TagValueList(list):
    """List to store tags in a Storage-object. The only difference to a usual python list is that a TagValueList stores a reference to the Storage-object and will notify the storage if the list is empty. The storage will then remove the list."""
    def __init__(self,storage,aList=None):
        list.__init__(self,aList if aList is not None else [])
        self.storage = storage
    
    def __setitem__(self,key,value):
        list.__setitem__(self,key,value)
        
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
        assert isinstance(key,Tag)
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


class TranslationFileHandler(xml.sax.handler.ContentHandler):
    """Content handler for tag translation files."""
    def startElement(self,name,attributes):
        if name == 'tag':
            if 'key' not in attributes:
                logger.warning("Incorrect tag translation file (key is missing).")
                return
            if 'name' not in attributes:
                logger.warning("Incorrect tag translation file (name is missing).")

            _translation[attributes['key']] = attributes['name']
