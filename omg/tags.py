# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""Module for tag handling.

This module provides methods to store tags, convert them between different values, to convert tag-ids to
tagnames and vice versa and so on. Call :func:`init` at program start to initialize the module using the
information in the ``tagids``-table and use one of the following ways to get tags:

    * The easiest way is the :func:`get-method<omg.tags.get>` which takes a tag-id or a tag-name as
      parameter.
    * Use :func:`fromTitle` to get tags from user input which may be in the user's language
      (e.g. ``'Künstler'``).
    * For some tags which have a special meaning to the program and cannot always be treated generically
      (e.g. the title-tag) there exist constants (e.g. ``TITLE``). This allows to use tags.TITLE instead of
      ``tags.get(options.tags.title_tag``) as the user may decide to use another tagname than ``'title'``
      for his titles.
    * To iterate over all tags use the module variable ``tagList``.
    * Only in the case that the tag in question is not already in the database you should (and must) create
      the :class:`Tag`-instance using the constructor of :class:`Tag`.
    
\ """
from collections import Sequence
from functools import reduce

from omg import config, constants, logging
from omg.utils import FlexiDate
from PyQt4 import QtGui

translate = QtGui.QApplication.translate
logger = logging.getLogger(__name__)


# Module variables - Will be initialized with the first call of init.
#=================================================================================
# Dictionaries of all indexed tags. From outside the module use the get-method instead of these private
# variables.
_tagsById = None
_tagsByName = None

# Dict mapping tagnames to their translation
_translation = None

# Local reference to the database, will be created in init
db = None

# List of all indexed tags in the order specified by the config-variable tags->tag_order (tags which are not
# contained in that list will appear in arbitrary order at the end of tagList). Us this to iterate over all
# tags.
tagList = None

# Tags which have a special meaning for the application and cannot always be treated generically.
# Will be initialized with the first call of init, so remember to change also that function whenever changing
# the following lines.
TITLE = None
ALBUM = None


class ValueType:
    """Class for the type of tag-values. Currently only three types are possible: varchar, date and text.
    For each of them there is an instance (e.g. ``tags.TYPE_VARCHAR``) and you can get all of them via
    ``tags.TYPES``. You should never create your own instances.
        
        - *name* is one of ''varchar'', ''date'', ''text''
        - *description* is a description that will be displayed to the user
        
    \ """
    def __init__(self,name,description):
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
        """Convert *value* from this type to *newType* and return the result. This method converts from
        :class:?omg.utils.FlexiDate` (type date) to strings (types varchar and text) and vice versa.
        If conversion fails or the converted value is not valid for *newType* (confer
        :meth:`ValueType.isValid`), this method will raise a :exc:`ValueError`.
        """
        if self == TYPE_DATE and newType != TYPE_DATE:
            convertedValue = value.strftime()
        elif self != TYPE_DATE and newType == TYPE_DATE:
            convertedValue = FlexiDate.strptime(value)
        else: convertedValue = value # nothing to convert
        if newType.isValid(convertedValue):
            return convertedValue
        else: raise ValueError("Converted value {} is not valid for valuetype {}."
                                 .format(convertedValue,newType))

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
        """Convert a string (which must be valid for this valuetype) to the preferred representation of
        values of this type. Actually this method does nothing than convert strings to
        :class:`omg.utils.FlexiDate`\ s if this is the date-type.
        """
        if self == TYPE_DATE:
            return FlexiDate.strptime(string)
        else: return string
    
    def __repr__(self):
        return 'ValueType({})'.format(self.name)
    
    def __str__(self):
        return self.name


# Module variables for the existing types
TYPE_VARCHAR = ValueType('varchar', translate('tags', 'a tag type for normal (not too long) text values'))
TYPE_TEXT = ValueType('text', translate('tags', 'a tag type for long texts (like e.g. lyrics)'))
TYPE_DATE = ValueType('date', translate('tags', 'a tag type for dates'))
TYPES = [TYPE_VARCHAR,TYPE_TEXT,TYPE_DATE]


class Tag:
    """
        A tagtype like ``'artist'``. ``'title'``, etc.. Tags have five public attributes:
        
            * ``id``: The id of the tag if it is in the database or None otherwise,
            * ``name``: The name of the tag,
            * ``type``: The value-type of this tag (e.g. varchar) as instance of :class:`omg.tags.ValueType`,
            * ``title``: A nice title to be displayed to the user (usually a translation of the name),
            * ``rawTitle``: The title as set in the database. If a tag does not have a title set in the
                database this will be None, while ``title`` will be the name.

        Usually you should get tag instances via the :func:`get-method<omg.tags.get>`. The exception is for
        tags that are not (yet) in the database (use :func:`exists` to check this). For these tags
        :func:`get` will fail and you have to create your own instances. If you use the common instance, it
        will get automatically updated on TagTypeChangeEvents.
    """
    def __init__(self,id,name,valueType,title,iconPath,private=False):
        if not isinstance(id,int) or not isinstance(name,str) or not isinstance(valueType,ValueType) \
                or (title is not None and not isinstance(title,str)):
            raise TypeError("Invalid type (id,name,valueType,title): ({},{},{},{}) of types ({},{},{},{})"
                            .format(id,name,valueType,title,type(id),type(name),type(valueType),type(title)))
        assert isValidTagname(name)
        self.id = id
        self.name = name.lower()
        self.type = valueType
        self.rawTitle = title
        self.setIconPath(iconPath)
        self.private = private

    def setIconPath(self,iconPath):
        """Set the tag's iconPath and load the icon."""
        assert iconPath is None or isinstance(iconPath,str)
        self.iconPath = iconPath
        if iconPath is not None:
            self.icon = QtGui.QIcon(iconPath)
        else: self.icon = None
        
    def isValid(self,value):
        """Return whether the given value is a valid tag-value for this tag (this depends only on the
        tag-type).
        """
        return self.type.isValid(value)
     
    def sqlFormat(self,value):
        """Convert *value* into a string that can be inserted into database queries."""
        return self.type.sqlFormat(value)
        
    def __eq__(self,other):
        return isinstance(other,Tag) and other.id == self.id
    
    def __ne__(self,other):
        return not isinstance(other,Tag) or other.id != self.id

    def __hash__(self):
        return self.id

    def __repr__(self):
        return '"{0}"'.format(self.name)

    def __str__(self):
        return self.title
    
    def getTitle(self):
        return self.rawTitle if self.rawTitle is not None else self.name
    
    def setTitle(self,title):
        if title != '':
            self.rawTitle = title
        else: self.rawTitle = None
        
    title = property(getTitle,setTitle)

        
class UnknownTagError(RuntimeError):
    """This exception class is raised by get and fromTitle, if they cannot find a tag
    matching the parameters.
    """
    def __init__(self, tagname):
        self.tagname = tagname
        
    def __str__(self):
        return 'Unknown tag {}'.format(self.tagname)


def isValidTagname(name):
    """Return whether *name* is a valid tag name. OMG uses the restrictions imposed by the
    Vorbis-specification: ASCII 0x20 through 0x7D, 0x3D ('=') excluded.
    Confer http://xiph.org/vorbis/doc/v-comment.html.
    """
    try:
        encoded = name.encode('ascii')
        return 0 < len(encoded) < 64 and all(0x20 <= c <= 0x7D and c != 0x3D for c in encoded)
    except UnicodeEncodeError:
        return False


def exists(identifier):
    """Return whether a tag with the id *identifier* (in case *identifier* is an integer) or the name
    *identifier* (in case it is a string) does exist.
    """
    if isinstance(identifier,int):
        return identifier in _tagsById
    elif isinstance(identifier,str):
        return identifier in _tagsByName
    else:
        raise RuntimeError("Identifier's type is neither int nor string: {} of type {}"
                                .format(identifier,type(identifier)))


def get(identifier, createDialogIfNew = False):
    """Return the tag identified by *identifier*. If *identifier* is an integer return the tag with this id.
    
    If *identifier* is a string return the tag with this name.
    If *identifier* is a Tag-instance, return *identifier*.
    This method does not create new instances of the tags but returns always the same instance.
    
    If *createDialogIfNew* is True, and there is no tag matching *identifier*, a dialog is popped up
    to create the new tag.
    """
    if isinstance(identifier,int):
        return _tagsById[identifier]
    elif isinstance(identifier,str):
        identifier = identifier.lower()
        if identifier in _tagsByName:
            return _tagsByName[identifier]
        elif createDialogIfNew:
            from .gui.tagwidgets import NewTagTypeDialog
            return NewTagTypeDialog.createTagType(identifier,
                                           text = 'specify type of tag "{}"'.format(identifier))
        else: raise UnknownTagError(identifier)
    elif isinstance(identifier, Tag):
        return identifier
    else:
        raise TypeError("Identifier's type is neither int nor string nor tag: {} of type {}"
                            .format(identifier,type(identifier)))


def isTitle(title):
    """Return whether *name* is the title of a known tag (comparison is case-insensitive!)."""
    return title.lower() in [str.lower(tag.title) for tag in tagList if tag.title is not None]


def fromTitle(title):
    """Return the tag of the given title (comparison is case-insensitive!). If no such tag
    exists, invoke get to return a tag. Use this method to get a tag from user input, especially when using
    combo-boxes with predefined values containing tag titles.
    """
    title = title.lower()
    for tag in tagList:
        if title == tag.title.lower():
            return tag
    else: return get(title)

    
def addTagType(name,valueType,title=None,iconPath=None,private=False,tagType=None):
    """Adds a new tag named *name* of type *valueType* and with title *title* to the database.
    If *private* is True, a private tag is created.
    
    Alternatively, if *tagType* is given, this tagtype with its id and data will be added to
    the database ignoring all other arguments. This is only used to undo a tagtype's deletion.
    
    After creation the dispatcher's TagTypeChanged signal is emitted.
    """
    from . import database as db
    from .modify import dispatcher, events, ADDED
    if tagType is not None:
        if title is None:
            title = name
        data = (tagType.id,tagType.name,tagType.type.name,tagType.title,tagType.iconPath,tagType.private)
        db.query(
            "INSERT INTO {}tagids (id,tagname,tagtype,title,icon,private) VALUES (?,?,?,?,?,?)"
              .format(db.prefix),*data)
        _tagsByName[tagType.name] = tagType
        _tagsById[tagType.id] = tagType
        tagList.append(tagType)
        dispatcher.changes.emit(events.TagTypeChangedEvent(ADDED,tagType))
        return tagType
        
    logger.info("Adding new tag '{}' of type '{}'.".format(name,valueType.name))
    name = name.lower()
    if name in _tagsByName:
        raise RuntimeError("Requested creation of tag {} which is already there".format(name))
    
    id = db.query(
        "INSERT INTO {}tagids (tagname,tagtype,title,icon,private) VALUES (?,?,?,?,?)".format(db.prefix),
        name,valueType.name,title,iconPath,private
        ).insertId()
    newTag = Tag(id,name,valueType,title,iconPath,private)
    _tagsByName[name] = newTag
    _tagsById[id] = newTag
    tagList.append(newTag)
    dispatcher.changes.emit(events.TagTypeChangedEvent(ADDED,newTag))
    return newTag


def removeTagType(tag):
    """Remove a tagtype from the database, including all its values and relations. This will not touch any
    files though!
    
    After removal the dispatcher's tagTypeChanged signal is emitted.
    """
    logger.info("Removing tag '{}'.".format(tag.name))
    if tag == TITLE or tag == ALBUM:
        raise ValueError("Cannot remove title or album tag.")
    
    from . import database
    database.query("DELETE FROM {}tagids WHERE id=?".format(database.prefix),tag.id)
    del _tagsByName[tag.name]
    del _tagsById[tag.id]
    tagList.remove(tag)
            
    from .modify import dispatcher, events, DELETED
    dispatcher.changes.emit(events.TagTypeChangedEvent(DELETED,tag))


def changeTagType(tag,name=None,valueType=None,title='',iconPath='',private=None):
    """Change a tagtype. In particular update the instance *tag* (this is usually the only instance of this
    tag) and the database. The other arguments determine what to change. Omit them to leave a property
    unchanged. This method will not touch any files though!
    
    After removal the dispatcher's tagTypeChanged signal is emitted.
    """
    oldName = tag.name
    assignments = []
    params = []
    
    if name is not None and name != tag.name:
        name = name.lower()
        if not isValidTagname(name):
            raise ValueError("'{}' is not a valid tagname.".format(name))
        assignments.append('tagname = ?')
        params.append(name)
        del _tagsByName[tag.name]
        _tagsByName[name] = tag
        tag.name = name
    
    if valueType is not None and name != tag.type:
        if not isinstance(valueType,ValueType):
            raise ValueError("'{}' is not a ValueType.".format(valueType))
        assignments.append('tagtype = ?')
        params.append(valueType.name)
        tag.type = valueType
    
    if title != '' and title != tag.title:
        assignments.append('title = ?')
        params.append(title)
        tag.title = title
        
    if iconPath != '' and iconPath != tag.iconPath:
        assignments.append('icon = ?')
        params.append(iconPath)
        tag.setIconPath(iconPath)
        
    if private is not None and bool(private) != tag.private:
        assignments.append('private = 1' if private else 'private = 0')
        tag.private = bool(private)
    
    if len(assignments) > 0:
        if tag.name != oldName:
            logger.info("Changing tag '{}' into {}.".format(oldName,tag.name))
        else: logger.info("Changing tag '{}'.".format(tag.name))
        from . import database
        database.query("UPDATE {}tagids SET {} WHERE id = {}"
                        .format(database.prefix,','.join(assignments),tag.id),
                        *params)
        
        from .modify import dispatcher, events, CHANGED
        dispatcher.changes.emit(events.TagTypeChangedEvent(CHANGED,tag))


def loadTagTypesFromDB():
    """Initialize _tagsById, _tagsByName and tagList from the database. Raise a runtime error when the 
    tags cannot be fetched from the database (e.g. because the tagids table is missing)."""
    global _tagsByName, _tagsById, tagList
    from omg import database as db
    _tagsById = {}
    _tagsByName = {}
    
    try:
        result = db.query("SELECT id,tagname,tagtype,title,icon,private FROM {}tagids"
                                  .format(db.prefix))
    except db.sql.DBException:
        logger.error("Could not fetch tags from tagids table.")
        raise RuntimeError()
        
    for row in result:
        id,tagName,valueType,title,iconPath,private = row
        if db.isNull(title) or title == "":
            title = None
            
        if db.isNull(iconPath):
            iconPath = None
        valueType = ValueType.byName(valueType)
        newTag = Tag(id,tagName,valueType,title,iconPath,private)
        _tagsById[newTag.id] = newTag
        _tagsByName[newTag.name] = newTag
        
    # tagList contains the tags in the order specified by config.options.tags.tag_order...
    tagList = [ _tagsByName[name] for name in config.options.tags.tag_order if name in _tagsByName ]
    # ...and then all remaining tags in arbitrary order
    tagList.extend(set(_tagsByName.values()) - set(tagList))
    
    
def init():
    """Initialize the variables of this module based on the information of the tagids-table and config-file.
    At program start or after changes of that table this method must be called to ensure the module has the
    correct tags and their IDs. Raise a RuntimeError when tags cannot be fetched from the database correctly.
    """
    global TITLE,ALBUM, _translation
    
    loadTagTypesFromDB()
        
    if config.options.tags.title_tag not in _tagsByName:
        logger.error("Title tag '{}' is missing in tagids table.".format(config.options.tags.title_tag))
        raise RuntimeError()
    if config.options.tags.album_tag not in _tagsByName:
        logger.error("Album tag '{}' is missing in tagids table.".format(config.options.tags.album_tag))
        raise RuntimeError()

    TITLE = _tagsByName[config.options.tags.title_tag]
    ALBUM = _tagsByName[config.options.tags.album_tag]


class TagValueList(list):
    """List to store tags in a :class:`omg.tags.Storage`-object. The only difference to a usual python list
    is that a TagValueList stores a reference to the Storage-object and will notify the storage if the list
    is empty. The storage will then remove the list.
    """
    def __init__(self,storage,aList=None):
        list.__init__(self,aList if aList is not None else [])
        self.storage = storage
    
    def __setitem__(self,key,value):
        list.__setitem__(self,key,value)
        
    def __delitem__(self,key):
        list.__delitem__(self,key)
        if len(self) == 0:
            self.storage._removeList(self)
            
    def remove(self,value):
        list.remove(self,value)
        if len(self) == 0:
            self.storage._removeList(self)
            
    def pop(self):
        value = list.pop(self)
        if len(self) == 0:
            self.storage._removeList(self)
        return value


class Storage(dict):
    """"Dictionary subclass used to store tags. As an element may have several values for the same tag,
    Storage maps tags to lists of tag-values. The class ensures that an instance never contains an empty
    list and adds a few useful functions to deal with such datastructures.
    """
    def __init__(self,*args):
        if len(args) == 1 and isinstance(args[0],dict):
            assert all(isinstance(v,TagValueList) for v in args[0].values())
        dict.__init__(self,*args)
    
    def copy(self):
        """Return a copy of this storage-object containing copies of the original tag-value-lists."""
        result = Storage({tag: TagValueList(self,l) for tag,l in self.items()})
        for tagValueList in result.values():
            tagValueList.storage = result
        return result
        
    def __setitem__(self,key,value):
        if not isinstance(key,Tag):
            raise ValueError("key argument must be a tag instance. I got {}".format(key))
        if not isinstance(value,Sequence) or isinstance(value,str):
            raise ValueError("value must be a Sequence (but no string. I got {}".format(key))
            
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
        """Add one or more values to the list of the given tag. If a value is already contained in the list,
        do not add it again.
        """
        if not isinstance(tag,Tag):
            tag = get(tag)
        if tag not in self:
            # Values may contain repetitions, so we need to filter them away.
            # Remember that self[tag] = [] won't work.
            newList = []
            for value in values:
                if value not in newList:
                    newList.append(value)
            self[tag] = newList
        else:
            for value in values:
                if value not in self[tag]:
                    self[tag].append(value)
                
    def remove(self,tag,*values):
        """Remove one or more values from the list of the given tag. If a value is not contained in this
        Storage just skip it.
        """
        if not isinstance(tag,Tag):
            tag = get(tag)
        for value in values:
            try:
                self[tag].remove(value)
            except ValueError: pass
            
    def replace(self,tag,oldValue,newValue):
        """Replace a value of *tag*. Because *newValue* will be at the same position where *oldValue* was,
        this might look nicer in displays, than simply removing *oldValue* and appending *newValue*.
        """
        if not isinstance(tag,Tag):
            tag = get(tag)
        for i,value in enumerate(self[tag]):
            if value == oldValue:
                self[tag][i] = newValue
                return
    
    def merge(self,other):
        """Add all tags from *other* to this storage. *other* may be another :class:`omg.tags.Storage`
        instance or a :func:`dict` mapping tags to value-lists. This method won't add already existing
        values again.
        """
        for tag,valueList in other.items():
            self.addUnique(tag,*valueList)
                
    def removeTags(self,other):
        """Remove all values from *other* from this storage. *other* may be another :class:`omg.tags.Storage`
        instance or a :func:`dict` mapping tags to value-lists. If *other* contains tags and values which are
        not contained in this storage, they will be skipped.
        """
        for tag,valueList in other.items():
            self.removeValues(tag,*valueList)

    def withoutPrivateTags(self):
        """Return a Storage-object containing the same tags but without private tags. If there are no private
        tags, return simply this object itself."""
        if any(tag.private for tag in self):
            return Storage({tag: l for tag,l in self.items() if not tag.private})
        else: return self


def findCommonTags(elements, recursive = True):
    """Returns a Storage object containing all tags that are equal in all of the elements. If recursive is
    True, also all children of the elements are considered.
    """
    if recursive:
        elems = set()
        for e in elements:
            elems.update(e.getAllNodes(skipSelf = False))
        elements = elems
    commonTags = set(reduce(lambda x,y: x & y, [set(elem.tags.keys()) for elem in elements ]))
    commonTagValues = {}
    differentTags=set()
    
    for element in elements:
        t = element.tags
        for tag in commonTags:
            if tag not in commonTagValues:
                commonTagValues[tag] = t[tag]
            elif commonTagValues[tag] != t[tag]:
                differentTags.add(tag)
    sameTags = commonTags - differentTags
    tags = Storage()
    for tag in sameTags:
        tags[tag] = commonTagValues[tag]
    return tags
