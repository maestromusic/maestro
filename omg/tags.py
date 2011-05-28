#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

"""Module for tag handling.

This module provides methods to store tags, convert them between different values, to convert tag-ids to tagnames and vice versa and so on. Call :func:`init` at program start to initialize the module using the information in the ``tagids``-table and use one of the following ways to get tags:

    * The easiest way is the :func:`get-method<omg.tags.get>` which takes a tag-id or a tag-name as parameter.
    * Use :func:`fromTranslation` to get tags from user input which may be in the user's language (e.g. ``'Künstler'``).
    * For some tags which have a special meaning to the program and cannot always be treated generically (e.g. the title-tag) there exist constants (e.g. ``TITLE``). This allows to use tags.TITLE instead of ``tags.get(options.tags.title_tag``) as the user may decide to use another tagname than ``'title'`` for his titles.
    * To iterate over all indexed tags use the module variable ``tagList``.
    * Only in the case that the tag in question is not already in the database you should (and must) create the :class:`Tag`-instance using the constructor of :class:`Tag`.
    
\ """
import os.path, xml.sax
from collections import Sequence
from xml.sax.handler import ContentHandler

from omg import config, constants, logging
from omg.utils import FlexiDate, getIconPath
import PyQt4
translate = PyQt4.QtGui.QApplication.translate
logger = logging.getLogger("omg.tags")

# Module variables - Will be initialized with the first call of init.
#=================================================================================
# Dictionaries of all indexed tags. From outside the module use the get-method instead of these private variables.
_tagsById = None
_tagsByName = None

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


class ValueType:
    """Class for the type of tag-values. Currently only three types are possible: varchar, date and text. For each of them there is an instance (e.g. ``tags.TYPE_VARCHAR``) and you can get all of them via ``tags.TYPES``. You should never create your own instances."""
    def __init__(self,name, description = ''):
        self.name = name
        self.description = description

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
                    return True
                except TypeError:
                    return False
                except ValueError:
                    return False
        else: assert False # should never happen

    def convertValue(self,newType,value):
        """Convert *value* from this type to *newType* and return the result. This method converts from :class:?omg.utils.FlexiDate` (type date) to strings (types varchar and text) and vice versa. If conversion fails or the converted value is not valid for *newType* (confer :meth:`ValueType.isValid`), this method will raise a :exc:`ValueError`."""
        if self == TYPE_DATE and newType != TYPE_DATE:
            convertedValue = value.strftime()
        elif self != TYPE_DATE and newType == TYPE_DATE:
            convertedValue = FlexiDate.strptime(value)
        else: convertedValue = value # nothing to convert
        if newType.isValid(convertedValue):
            return convertedValue
        else: raise ValueError("Converted value {} is not valid for valuetype {}.".format(convertedValue,newType))

    def sqlFormat(self,value):
        """Convert *value* into a string that can be inserted into database queries."""
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
        else: raise IndexError("There is no valuetype with name '{}'.".format(name))

    def valueFromString(self,string):
        """Convert a string (which must be valid for this valuetype) to the preferred representation of values of this type. Actually this method does nothing than convert strings to :class:`omg.utils.FlexiDate`\ s if this is the date-type."""
        if self == TYPE_DATE:
            return FlexiDate.strptime(string)
        else: return string
    
    def __repr__(self):
        return 'ValueType({})'.format(self.name)
    
    def __str__(self):
        return self.name

# Modul variables for the existing types
TYPE_VARCHAR = ValueType('varchar', translate('tags', 'a tag type for normal (not too long) text values'))
TYPE_TEXT = ValueType('text', translate('tags', 'a tag type for long texts (like e.g. lyrics)'))
TYPE_DATE = ValueType('date', translate('tags', 'a tag type for dates'))
TYPES = [TYPE_VARCHAR,TYPE_TEXT,TYPE_DATE]


class Tag:
    """
        A tag like ``'artist'``. ``'title'``, etc.. Tags have three public attributes:
        
            * ``id``: The id of the tag if it is in the database or None otherwise,
            * ``name``: The name of the tag,
            * ``type``: The type as instance of :class:`omg.tags.ValueType`.

        Usually you shold get tag instances via the :func:`get-method<omg.tags.get>`. The exception is for tags that are not (yet) in the database (use :func:`exists` to check this). For these tags :func:`get` will fail and you have to create your own instances. 

        Tags contain a tagname and compare equal if and only this tagname is equal. Tags may be used as dictionary keys.
    """
    def __init__(self,id,name,valueType):
        if not isinstance(id,int) or not isinstance(name,str) or not isinstance(valueType,ValueType):
            raise TypeError("Invalid type (id,name,valueType): ({},{},{}) of types ({},{},{})"
                                .format(id,name,valueType,type(id),type(name),type(valueType)))
        if not Tag.isValidTagname(name):
            raise ValueError("Invalid tagname '{}'".format(name))
        self.id = id
        self.name = name.lower()
        self.type = valueType

    def isValid(self,value):
        """Return whether the given value is a valid tag-value for this tag (this depends only on the tag-type)."""
        return self.type.isValid(value)
     
    def sqlFormat(self,value):
        """Convert *value* into a string that can be inserted into database queries."""
        return self.type.sqlFormat(value)
        
    def __eq__(self,other):
        if other is None or not isinstance(other,Tag):
            return False
        else:
            if self.id is not None and other.id is not None:
                return self.id == other.id
            else: return self.name == other.name
    
    def __ne__(self,other):
        if other is None or not isinstance(other,Tag):
            return True
        else:
            if self.id is not None and other.id is not None:
                return self.id != other.id
            else: return self.name != other.name

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

    def __repr__(self):
        return '"{0}"'.format(self.name)

    def __str__(self):
        return self.name
        
    def translated(self):
        """Return the translation of this tag in the user's language. In most cases you will want to display this string rather than ``tag.name``."""
        return _translation.get(self.name,self.name) # if self.name is not contained in the dict return the name itself
    
    def iconPath(self):
        """Return the path to the icon of this tag or ``None`` if there is no such icon."""
        path = getIconPath("tag_{}.png".format(self.name))
        return path if os.path.isfile(path) else None

    @staticmethod
    def isValidTagname(name):
        """Return whether *name* is a valid tag name. OMG uses the restrictions imposed by the Vorbis-specification: ASCII 0x20 through 0x7D, 0x3D ('=') excluded. Confer http://xiph.org/vorbis/doc/v-comment.html."""
        try:
            return all(0x20 <= c <= 0x7D and c != 0x3D for c in name.encode('ascii'))
        except UnicodeEncodeError:
            return False


def exists(identifier):
    """Return whether a tag with the id *identifier* (in case *identifier* is an integer) or the name *identifier* (in case it is a string) does exist."""
    if isinstance(identifier,int):
        return identifier in _tagsById
    elif isinstance(identifier,str):
        return identifier in _tagsByName
    else:
        raise RuntimeError("Identifier's type is neither int nor string: {} of type {}"
                                .format(identifier,type(identifier)))
        
class UnknownTagError(RuntimeError):
    tagname = None
    def __init__(self, tagname):
        self.tagname = tagname
    def __str__(self):
        return 'unknown tag {}'.format(self.tagname)

def get(identifier):
    """Return the tag identified by *identifier*. If *identifier* is an integer return the tag with this id.
    If *identifier* is a string return the tag with this name.
    If *identifier* is a Tag-instance, return *identifier*.
    This method does not create new instances of the tags but returns always the same instance."""
    if isinstance(identifier,int):
        return _tagsById[identifier]
    elif isinstance(identifier,str):
        identifier = identifier.lower()
        if identifier in _tagsByName:
            return _tagsByName[identifier]
        else:
            raise UnknownTagError(identifier)
    elif isinstance(identifier, Tag):
        return identifier
    else:
        raise TypeError("Identifier's type is neither int nor string nor tag: {} of type {}"
                            .format(identifier,type(identifier)))


def fromTranslation(translation):
    """Return the tag whose translation is *translation* (comparison is case-insensitive!). If no such tag exists, invoke get to return a tag. Use this method to get a tag from user input, especially when using combo-boxes with predefined values containing translated tags."""
    translation = translation.lower()
    for key,name in _translation.items():
        if name.lower() == translation:
            return get(key)
    else: return get(translation)


def addTag(name, type, sort = None, private = False):
    """Adds a new tag named <name> of type <type> to the database. The parameter <sort> is the tag by which elements should
    be sorted if displayed below a ValueNode of this new tag; this defaults to the TITLE tag.
    If private is True, a private tag is created.""" 
    if name in _tagsByName:
        raise RuntimeError("Requested creation of tag {} which is already there".format(name))
    if sort is None:
        sort = TITLE
    from omg import database
    id = database.query(
        "INSERT INTO {}tagids (tagname,tagtype, sortkey, private) VALUES (?, ?, ?, ?)".format(database.prefix),
        name,type.name, sort.id, private).insertId()
    newTag = Tag(id,name,type)
    _tagsByName[name] = newTag
    _tagsById[id] = newTag
    tagList.append(newTag)
    #TODO: Popularize the new tag
    return newTag


def init():
    """Initialize the variables of this module based on the information of the tagids-table and config-file. At program start or after changes of that table this method must be called to ensure the module has the correct tags and their IDs."""
    global _tagsById,_tagsByName,tagList, _translation

    # Initialize _tagsById, _tagsByName and tagList from the database
    from omg import database
    _tagsById = {}
    _tagsByName = {}
    for row in database.query("SELECT id,tagname,tagtype FROM {}tagids".format(database.prefix)):
        newTag = Tag(row[0],row[1],ValueType.byName(row[2]))
        _tagsById[newTag.id] = newTag
        _tagsByName[newTag.name] = newTag
    
    # tagList contains the tags in the order specified by tags->tag_order...
    tagList = [ _tagsByName[name] for name in config.options.tags.tag_order if name in _tagsByName ]
    # ...and then all remaining tags in arbitrary order
    tagList.extend(set(_tagsByName.values()) - set(tagList))

    # Initialize _translation
    _translation = {}
    files = [os.path.join('i18n','tags.'+config.options.i18n.locale+'.xml'),
             os.path.join('i18n','tags.'+config.options.i18n.locale[:2]+'.xml')] #try de instead of de_DE
    if all(not os.path.exists(file) for file in files):
        logger.warning("I could not find a tag translation file for locale '{}'.".format(config.options.i18n.locale))
    else:
        for file in files:
            if os.path.exists(file):
                try:
                    xml.sax.parse(file,TranslationFileHandler())
                except xml.sax.SAXParseException as e:
                    logger.warning("I could not parse tag translation file '{}'. Error message: {}"
                                        .format(file,e.message()))
    
    global TITLE,ALBUM
    if config.options.tags.title_tag not in _tagsByName:
        raise RuntimeError("Cannot find a '{}'-tag in the database.".format(config.options.tags.title_tag))
    if config.options.tags.album_tag not in _tagsByName:
        raise RuntimeError("Cannot find a '{}'-tag in the database.".format(config.options.tags.album_tag))
    TITLE = _tagsByName[config.options.tags.title_tag]
    ALBUM = _tagsByName[config.options.tags.album_tag]


class TagValueList(list):
    """List to store tags in a :class:`omg.tags.Storage`-object. The only difference to a usual python list is that a TagValueList stores a reference to the Storage-object and will notify the storage if the list is empty. The storage will then remove the list."""
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
        """Add all tags from *other* to this storage. *other* may be another :class:`omg.tags.Storage`-instance or a :func:`dict` mapping tags to value-lists. This method won't add already existing values again."""
        for tag,valueList in other.items():
            self.addUnique(tag,*valueList)
                
    def removeTags(self,other):
        """Remove all values from *other* from this storage. *other* may be another :class:`omg.tags.Storage`-instance or a :func:`dict` mapping tags to value-lists. If *other* contains tags and values which are not contained in this storage, they will be skipped."""
        for tag,valueList in other.items():
            self.removeValues(tag,*valueList)


class TranslationFileHandler(xml.sax.handler.ContentHandler):
    """Content handler for tag translation files. When it parses a file it will store all translations in the internal module variable ``_translation``."""
    def startElement(self,name,attributes):
        if name == 'tag':
            if 'key' not in attributes:
                logger.warning("Incorrect tag translation file (key is missing).")
                return
            if 'name' not in attributes:
                logger.warning("Incorrect tag translation file (name is missing).")

            _translation[attributes['key']] = attributes['name']
