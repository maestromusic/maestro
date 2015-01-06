# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2015 Martin Altmayer, Michael Helmling
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

This module provides methods and structures

    * to manage tag types: convert tag ids to tag names and vice versa, add tag types to the database and
      remove them again, modify tag types (icon, title etc.)
    * to store tags in elements (or elsewhere)

There is one tag type for each valid tag name. Some tag types are stored in the database and called 'internal'
while the other ones are called 'external'. Internal tags have an id, a type and may have a title, an icon
or be private (i.e. they will not be stored in files but only in the database).

For each tag type there can be only one instance of Tag which is created in the init-method for internal tags
or when the get-method is invoked for the first time with the type's tag name. 

Call init at program start to initialize the module using the information in the tagids-table and use one of 
the following ways to get tags:

    * The easiest way is the get-method which takes a tag-id or a tag-name as parameter. Because you must
      never create your own Tag instances, this is the only method to get instances of external tags.
    * Use fromTitle to get tags from user input which may be in the user's language
      (e.g. ``'Künstler'``).
    * For some tags which have a special meaning to the program and cannot always be treated generically
      (e.g. the title-tag) there exist constants (e.g. TITLE). This allows to use tags.TITLE instead of
      tags.get(options.tags.title_tag). Do not use tags.get('title') as the user may decide to use another
      tag name than 'title' for his titles.
    * To iterate over all internal tags in the user-defined order use the module variable tagList.
    
\ """
from collections import Sequence
from functools import reduce

from PyQt4 import QtGui

from .. import application, config, logging, utils, stack
from ..application import ChangeEvent, ChangeType

translate = QtGui.QApplication.translate


# Module variables - Will be initialized with the first call of init.
#=================================================================================
# Dictionaries of all indexed tags. From outside the module use the get-method instead of these private
# variables.
_tagsById = None
_tagsByName = None

# Dict mapping tag names to their translation
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

# Maximum length of encoded names and titles of tags
MAX_NAME_LENGTH = 63
# Maximum length of encoded values for varchar-tags
TAG_VARCHAR_LENGTH = 255


class TagValueError(ValueError):
    """This error is emitted by Tag.convertValue and ValueType.convertValue if a value cannot be converted
    into a different value-type."""
    pass


def init():
    """Initialize the variables of this module based on the information of the tagids-table and config-file.
    At program start or after changes of that table this method must be called to ensure the module has the
    correct tags and their IDs. Raise a RuntimeError when tags cannot be fetched from the database correctly.
    """
    global TITLE, ALBUM, db
    from .. import database as db
    
    if db.prefix+'tagids' not in db.listTables():
        logging.error(__name__, "tagids-table is missing")
        raise RuntimeError()
    
    loadTagTypesFromDB()

    TITLE = get(config.options.tags.title_tag)
    ALBUM = get(config.options.tags.album_tag)
    
    
def loadTagTypesFromDB():
    """Initialize _tagsById, _tagsByName and tagList from the database. Raise a runtime error when the 
    tags cannot be fetched from the database (e.g. because the tagids table is missing)."""
    global _tagsByName, _tagsById, tagList
    _tagsById = {}
    _tagsByName = {}
    tagList = []
    
    try:
        result = db.query("SELECT id, tagname, tagtype, title, icon, private FROM {p}tagids ORDER BY sort")
    except db.DBException:
        logging.error(__name__, "Could not fetch tags from tagids table.")
        raise RuntimeError()
        
    for row in result:
        id, tagName, valueType, title, iconPath, private = row
        if db.isNull(title) or title == "":
            title = None
            
        if db.isNull(iconPath):
            iconPath = None
        valueType = ValueType.byName(valueType)
        newTag = Tag(tagName, id, valueType, title, iconPath, private)
        _tagsById[newTag.id] = newTag
        _tagsByName[newTag.name] = newTag
        tagList.append(newTag)


class ValueType:
    """Class for the type of tag-values. Currently only three types are possible: varchar, date and text.
    For each of them there is an instance (e.g. tags.TYPE_VARCHAR) and you can get all of them via
    tags.TYPES or using the tags.TYPE_* constants. You must not create your own instances.
        
        - *name* is one of ''varchar'', ''date'', ''text''
        - *description* is a description that will be displayed to the user
        
    """
    def __init__(self, name, description):
        self.name = name
        self.description = description

    @staticmethod
    def byName(name):
        """Given a type-name return the corresponding instance of this class."""
        for type in TYPES:
            if type.name == name:
                return type
        else: raise IndexError("There is no value type with name '{}'.".format(name))
        
    def isValid(self, value):
        """Return whether the given value is a valid tag-value for tags of this type."""
        if self.name == 'varchar':
            return isinstance(value, str) and 0 < len(value.encode()) <= TAG_VARCHAR_LENGTH
        elif self.name == 'text':
            return isinstance(value, str) and len(value) > 0
        elif self.name == 'date':
            return isinstance(value, utils.FlexiDate)
        else: assert False

    def convertValue(self, value, crop=False, logCropping=True):
        """Convert *value* to this type and return the result. If conversion fails, raise a TagValueError.
        If *crop* is True, this method may crop *value* to make it valid (e.g. if *value* is too long for
        a varchar). If *logCropping* is True, cropping will print a logger warning.
        """
        if self.name == 'varchar':
            string = str(value)
            if len(string) == 0:
                raise TagValueError("varchar tags must have length > 0")
            if len(string.encode()) > TAG_VARCHAR_LENGTH:
                if crop:
                    if logCropping:
                        logging.warning(__name__,
                                        'Cropping a string that is too long for varchar tags: {}...'
                                       .format(string[:30]))
                    # Of course this might split in the middle of a unicode character. But errors='ignore'
                    # will silently remove the fragments 
                    encoded = string.encode()[:TAG_VARCHAR_LENGTH]
                    return encoded.decode(errors='ignore')
                else: raise TagValueError("String is too long for a varchar tag: {}...".format(string[:30]))
            return string
        elif self.name == 'text':
            string = str(value)
            if len(string) > 0:
                return string
            else: raise TagValueError("text tags must have length > 0")
        elif self.name == 'date':
            if isinstance(value, utils.FlexiDate):
                return value
            else:
                string = str(value)
                try:
                    return utils.FlexiDate.strptime(string, crop, logCropping)
                except ValueError as e:
                    raise TagValueError(str(e))
        else: assert False

    def canConvert(self, value, crop=False):
        """Return whether *value* can be converted into this type using convertValue. For *crop* see
        convertValue.
        """
        try:
            self.convertValue(value, crop, logCropping=False)
        except TagValueError:
            return False
        else: return True

    def sqlFormat(self, value):
        """Convert *value* into a string that can be inserted into database queries."""
        if self.name == 'varchar':
            if len(value.encode()) > TAG_VARCHAR_LENGTH:
                logging.error(__name__,
                              "Attempted to encode the following string for a varchar column although its "
                              "encoded size exceeds TAG_VARCHAR_LENGTH. The string will be "
                              "truncated: '{}'.".format(value))
            return value
        elif self.name == 'text':
            return value
        elif self.name == 'date':
            return value.toSql()
        else: assert False
    
    def fileFormat(self, value):
        """Return value as a string suitable for writing to a file. This currently makes a difference only
        for date tags which are always written as yyyy-mm-dd."""
        if self.name == 'date':
            return value.strftime(format = ("{Y:04d}", "{Y:04d}-{m:02d}", "{Y:04d}-{m:02d}-{d:02d}"))
        return value
    
    def __repr__(self):
        return 'ValueType({})'.format(self.name)
    
    def __str__(self):
        return self.name


# Module variables for the existing types
TYPE_VARCHAR = ValueType('varchar', translate("tags", "Standard type for normal (not too long) text values"))
TYPE_TEXT = ValueType('text', translate("tags", "Type for long texts (like e.g. lyrics)"))
TYPE_DATE = ValueType('date', translate("tags", "Type for dates"))
TYPES = [TYPE_VARCHAR, TYPE_TEXT, TYPE_DATE]
    
    
class Tag:
    """
        A tag type like 'artist'. 'title', etc.. Public attributes of tags are
        
            * id: The id of the tag. This is None for tags that are not in the database.
            * name: The name of the tag,
            * type: The value-type of this tag (e.g. varchar) as instance of ValueType,
            * title: A nice title to be displayed to the user (usually a translation of the name),
            * rawTitle: The title as set in the database. If a tag does not have a title set in the
              database this will be None, while 'title' will be the name. rawTitles must be unique (or None).
            * iconPath: Path to the tag type's icon or None if if doesn't have an icon.
            * icon: A QIcon loaded from above path (read-only)
            * private: Whether the tag is private, i.e. stored only in the database and not in files.

        You must use the get-method to get instances of this class. This method will ensure that there is
        always only one instance of a given tag and that this instance is updated automatically on
        TagTypeChangeEvents.
    """
    def __init__(self, name, id=None, type=None, title=None, iconPath=None, private=False):
        self.id = id
        self.name = name
        self.type = type
        self.rawTitle = title
        self.iconPath = iconPath
        self.private = private
    
    def _getData(self):
        """Return some attributes as dict."""
        return {'id': self.id,
                'type':self.type,
                'title': self.rawTitle,
                'iconPath': self.iconPath,
                'private': self.private
                }
    
    def _setData(self, data):
        """Set some attributes from a dict created with _getData."""
        # self.__dict__.update(data)  would be nicer but doesn't work with properties
        if 'id' in data:
            self.id = data['id']
        if 'type' in data:
            self.type = data['type']
        if 'title' in data:
            self.rawTitle = data['title']
        if 'iconPath' in data:
            self.iconPath = data['iconPath'] # invoke iconPath setter
        if 'private' in data:
            self.private = data['private']
    
    def _clearData(self):
        """Clear some attributes. This happens when adding a tag type to the database is undone."""
        self.id, self.type, self.rawTitle, self.iconPath, self.private = None, None, None, None, False
    
    def isInDb(self):
        """Return whether this tag type is internal, i.e. contained in the database."""
        return self.id is not None
    
    @property
    def title(self):
        return self.rawTitle if self.rawTitle is not None else self.name
        
    @property
    def icon(self):
        return self._icon
    
    @property
    def iconPath(self):
        return self._iconPath

    @iconPath.setter
    def iconPath(self, iconPath):
        """Set the tag type's iconPath and load the icon."""
        assert iconPath is None or isinstance(iconPath, str)
        self._iconPath = iconPath
        if iconPath is not None:
            self._icon = QtGui.QIcon(iconPath)
        else: self._icon = None
        
    def isValid(self, value):
        """Return whether the given value is a valid tag-value for this tag (this depends only on the
        tag-type).
        """
        if self.type is not None:
            return self.type.isValid(value)
        else: return True

    def convertValue(self, value, crop=False, logCropping=True):
        """Convert a value to this tag type. Raise a TagValueError if conversion is not possible.
        If *crop* is True, this method may crop *value* to make it valid (e.g. if *value* is too long for
        a varchar). If *logCropping* is True, cropping will print a logger warning.
        """
        if self.type is None:
            return str(value)
        else: return self.type.convertValue(value, crop)
    
    def canConvert(self, value, crop=False):
        """Return whether *value* can be converted into this type using convertValue. For *crop* see
        convertValue.
        """
        try:
            self.convertValue(value, crop, logCropping=False)
        except TagValueError:
            return False
        else: return True
        
    def fileFormat(self, string):
        """Format a value suitable for writing to a file."""
        if self.type is not None:
            return self.type.fileFormat(string)
        return string
    
    def sqlFormat(self, value):
        """Convert *value* into a string that can be inserted into database queries."""
        if self.type is None:
            raise ValueError("sqlFormat can only be used with internal tags, not for {}".format(self))
        return self.type.sqlFormat(value)

    def __repr__(self):
        return '"{}"'.format(self.name)

    def __str__(self):
        return self.title


def isValidTagName(name):
    """Return whether *name* is a valid tag name. Maestro uses the restrictions imposed by the
    Vorbis-specification: ASCII 0x20 through 0x7D, 0x3D ('=') excluded.
    Confer http://xiph.org/vorbis/doc/v-comment.html.
    
    Some tagnames are explicitly forbidden (tracknumber and discnumber).
    """
    if name.lower() in ['tracknumber', 'discnumber']:
        return False
    try:
        encoded = name.encode('ascii')
        return 0 < len(encoded) <= MAX_NAME_LENGTH and all(0x20 <= c <= 0x7D and c != 0x3D for c in encoded)
    except UnicodeEncodeError:
        return False


def isInDb(name):
    """Return whether a tag with the given name exists in the database."""
    return name in _tagsByName and _tagsByName[name].isInDb()


def get(identifier, addDialogIfNew=False):
    """Return the tag identified by *identifier*:
    
        If *identifier* is an integer return the tag with this id.
        If *identifier* is a string return the tag with this name. 
        If *identifier* is a Tag-instance, return *identifier*.
        
    This method does never create a second instance of one tag.
    """
    if isinstance(identifier, int):
        return _tagsById[identifier]
    elif isinstance(identifier, str):
        identifier = identifier.lower()
        if identifier in _tagsByName:
            return _tagsByName[identifier]
        else:
            if not isValidTagName(identifier):
                raise ValueError("'{}' is not a valid name for a tag-type".format(identifier))
            newTag = Tag(identifier)
            _tagsByName[identifier] = newTag
            if addDialogIfNew:
                from ..gui.tagwidgets import AddTagTypeDialog
                AddTagTypeDialog.addTagType(newTag)
            return newTag
    elif isinstance(identifier, Tag):
        return identifier
    else:
        raise TypeError("Identifier's type is neither int nor string nor tag: {} of type {}"
                            .format(identifier, type(identifier)))


def titleAllowed(title: str, forTag: Tag=None) -> bool:
    """Return whether *title* is an allowed tag title. Checks if any other tag has the same title
    already (case-insensitive). If *forTag* is given, that tag is excluded from the check (allows
    to change casing of a tag title).
    """
    if title is None:
        return True
    for tag in tagList:
        if tag.rawTitle is not None and tag is not forTag:
            if title.lower() == tag.rawTitle.lower():
                return False
    return True


def fromTitle(title):
    """Return the tag of the given title (comparison is case-insensitive!). If no such tag
    exists, invoke 'get' to return a tag. Use this method to get a tag from user input, especially when using
    combo-boxes with predefined values containing tag titles.
    """
    title = title.lower()
    for tag in tagList:
        if title == tag.title.lower():
            return tag
    else: return get(title)

    
def addTagType(tagType, type, **data):
    """Add a tag type to the database. *tagType* can be a valid tag name or an external tag type. Using
    keyword arguments you can optionally set attributes of the tag type which external tag types don't have
    Allowed keys are
        title, iconPath, private and index (the index of the tag type within tags.tagList).
        
    If the type cannot be added because an element contains a value which is invalid for the chosen type,
    a TagValueError is raised.
    """
    if isinstance(tagType, str):
        tagType = get(tagType)
    if tagType.isInDb():
        raise ValueError("Cannot add tag '{}' because it is already in the DB.".format(tagType))
    if 'title' in data:
        if titleAllowed(data['title']):
            raise ValueError("Cannot add tag '{}' with title '{}' because that title exists already."
                             .format(tagType, data['title']))
            
    stack.beginMacro(translate("Tags", "Add tag type to DB"))
    try:
        # External tags may have every value. We need to make sure that all can be converted to the new type.
        _convertTagTypeOnLevels(tagType, type)
    except TagValueError as error:
        stack.abortMacro()
        raise error

    data['type'] = type
    stack.push('', stack.Call(_addTagType, tagType, data), stack.Call(_removeTagType, tagType))
    stack.endMacro()
    return tagType
        
    
def _addTagType(tagType, data):
    """Similar to addTagType, but not undoable. *tagType* must be an external Tag instance. *data* may
    contain additional attributes, see Tag._setData. It must contain 'type'. When it does not contain 'id',
    this method will choose an id and store it in data['id'].
    """
    assert tagType.name in _tagsByName # if the tag was created with get, it is already contained there
    assert 'type' in data
    
    if 'index' in data:
        index = data['index']
    else: index = len(tagList)   
    
    db.query("UPDATE {p}tagids SET sort=sort+1 WHERE sort >= ?", index)
 
    tagType._setData(data)
    tagList.insert(index, tagType)
    
    if tagType.id is not None: # id has been set in _setData
        dataTuple = (tagType.id, tagType.name, tagType.type.name, tagType.rawTitle,
                tagType.iconPath, tagType.private, index)
        db.query( "INSERT INTO {p}tagids (id, tagname, tagtype, title, icon, private, sort) "
                  "VALUES (?,?,?,?,?,?,?)", *dataTuple)
    else:
        # The difference to the if-part is that we have to get the id from the database
        dataTuple = (tagType.name, tagType.type.name, tagType.rawTitle,
                     tagType.iconPath, tagType.private, index)
        tagType.id = db.query(
            "INSERT INTO {p}tagids (tagname, tagtype, title, icon, private, sort) VALUES (?,?,?,?,?,?)",
            *dataTuple).insertId()
        # Store id so that when this tag is added to the database again (after undo),
        # it will get the same id.
        data['id'] = tagType.id
    logging.info(__name__, "Added new tag '{}' of type '{}'.".format(tagType.name, tagType.type.name))

    _tagsById[tagType.id] = tagType
    application.dispatcher.emit(TagTypeChangeEvent(ChangeType.added, tagType))
    

def removeTagType(tagType):
    """Remove a tag type from the database. The tag type must not be contained in any internal elements!
    """
    if not tagType.isInDb():
        raise ValueError("Cannot remove external tag type '{}' from DB.".format(tagType))
    if tagType in (TITLE, ALBUM):
        raise ValueError("Cannot remove title or album tag.")
    if db.query("SELECT COUNT(*) FROM {p}tags WHERE tag_id = ?", tagType.id).getSingle() > 0:
        raise ValueError("Cannot remove a tag that appears in internal elements.")
    
    stack.beginMacro(translate("Tags", "Remove tag type from DB"))
    try:
        _convertTagTypeOnLevels(tagType, None)
    except TagValueError as error:
        stack.abortMacro()
        raise error

    data = tagType._getData()
    data['index'] = tagList.index(tagType)
    stack.push('', stack.Call(_removeTagType, tagType), stack.Call(_addTagType, tagType, data))
    stack.endMacro()
    
    
def _removeTagType(tagType):
    """Like removeTagType, but not undoable: Remove a tag type from the database, including all its values
    and relations. This will not touch any files though!
    """
    logging.info(__name__, "Removing tag type '{}'.".format(tagType.name))
    db.query("DELETE FROM {p}tagids WHERE id=?", tagType.id)
    db.query("UPDATE {p}tagids SET sort=sort-1 WHERE sort > ?", tagList.index(tagType))
    del _tagsById[tagType.id]
    tagList.remove(tagType)
    tagType._clearData()
    application.dispatcher.emit(TagTypeChangeEvent(ChangeType.deleted, tagType))
    

def changeTagType(tagType, **data):
    """Change an internal tag type. In particular update the single instance *tagType* and the database.
    The keyword arguments determine which properties should be changed::

        changeTagType(tagType, title='Artist', iconPath=None)
        
    Allowed keyword arguments are type, title, iconPath, private. If the type or private is changed,
    the tag type must not appear in any internal elements.
    If the type cannot be changed because an (external) element contains a value which is invalid for the new
    type, a TagValueError is raised.
    """
    if not tagType.isInDb():
        raise ValueError("Cannot change an external tag type '{}'.".format(tagType))
    if ('type' in data and data['type'] != tagType.type) \
            or ('private' in data and data['private'] != tagType.private):
        if db.query("SELECT COUNT(*) FROM {p}tags WHERE tag_id = ?", tagType.id).getSingle() > 0:
            raise ValueError("Cannot change the type of a tag that appears in internal elements.")
    
    stack.beginMacro(translate("Tags", "Change tag type"))
    if 'type' in data and data['type'] != tagType.type:
        try:
            _convertTagTypeOnLevels(tagType, data['type'])
        except TagValueError as error:
            stack.abortMacro()
            raise error
        
    stack.push('', stack.Call(_changeTagType, tagType, data),
               stack.Call(_changeTagType, tagType, tagType._getData()))
    stack.endMacro()
    
    
def _changeTagType(tagType, data):
    """Like changeTagType, but not undoable."""
    assert tagType.isInDb()
    
    # Below we will build a query like UPDATE tagids SET ... using the list of assignments (e.g. tagtype=?).
    # The parameters will be sent with the query to replace the question marks.
    assignments = []
    params = []
    
    if 'type' in data and data['type'] != tagType.type:
        type = data['type']
        if not isinstance(type, ValueType):
            raise ValueError("'{}' is not a ValueType.".format(type))
        logging.info(__name__, "Changing type of tag '{}' from '{}' to '{}'."
                               .format(tagType.name, tagType.type.name, type.name))
        assignments.append('tagtype = ?')
        params.append(type.name)
        tagType.type = type
    
    if 'title' in data and data['title'] != tagType.rawTitle:
        title = data['title']
        if title is not None and len(title) == 0:
            title = None
        assignments.append('title = ?')
        params.append(title)
        tagType.rawTitle = title
        
    if 'iconPath' in data and data['iconPath'] != tagType.iconPath:
        assignments.append('icon = ?')
        params.append(data['iconPath'])
        tagType.iconPath = data['iconPath']
        
    if 'private' in data and bool(data['private']) != tagType.private:
        assignments.append('private = 1' if data['private'] else 'private = 0')
        tagType.private = bool(data['private'])
    
    if len(assignments) > 0:
        params.append(tagType.id) # for the WHERE clause
        db.query("UPDATE {p}tagids SET "+','.join(assignments)+" WHERE id = ?", *params)
        application.dispatcher.emit(TagTypeChangeEvent(ChangeType.changed, tagType))


def _convertTagTypeOnLevels(tagType, valueType):
    """Convert all occurences of *tagType* on all levels from *tagType*'s value-type to *valueType*.
    
    This method is used to adjust levels just before a tag-type's value-type changes. *valueType*
    may be None, indicating that *tagType* is going to become an external tag.
    Before any level is changed this method checks whether all values can be converted. If not, a
    TagValueError is raised.
    """
    from . import levels
    changes = []
    for level in levels.allLevels:
        diffs = {}
        for element in level.elements.values(): # only external elements possible => won't take too long
            if tagType in element.tags:
                oldValues = element.tags[tagType]
                newValues = list(map(valueType.convertValue if valueType is not None else str, oldValues))
                if oldValues != newValues:
                    diffs[element] = SingleTagDifference(tagType, 
                                                         replacements=list(zip(oldValues, newValues)))
        if len(diffs) > 0:
            changes.append((level, diffs))
            
    # Only start changing levels if all tag value conversions have been successful.
    if len(changes):
        for level, diffs in changes:
            level.changeTags(diffs)
        

class TagTypeChangeEvent(ChangeEvent):
    """TagTypeChangeEvents are used when a tag type (like artist, composer...) is added, changed or removed.
    """
    def __init__(self, action, tagType):
        self.action = action
        self.tagType = tagType
  
    
def moveTagType(tagType, newIndex):
    """Move *tagType* to the given index within tagList."""
    index = tagList.index(tagType)
    if index == newIndex:
        return
    newList = tagList[:]
    del newList[index]
    newList.insert(newIndex, tagType)
    moveTagTypes(newList)
    
    
def moveTagTypes(newList):
    """Replace tagList by *newList*. Both lists must contain the same tag types!."""
    stack.push(translate("Tags", "Move tag types"),
                         stack.Call(_moveTagTypes, newList),
                         stack.Call(_moveTagTypes, tagList))


def _moveTagTypes(newList):
    """Like moveTagTypes, but not undoable.""" 
    global tagList
    if set(tagList) != set(newList):
        raise ValueError("*newList* must contain the same tags as tags.tagList")
    db.multiQuery("UPDATE {p}tagids SET sort = ? WHERE id = ?", enumerate([t.id for t in newList]))
    tagList = newList
    application.dispatcher.emit(TagTypeOrderChangeEvent())
        

class TagTypeOrderChangeEvent(ChangeEvent):
    """This event is emitted when the order of tag types has changed. The order is always stored in
    tags.tagList."""
    pass


class TagValueList(list):
    """List to store tags in a Storage-object. The only difference to a usual python list
    is that a TagValueList stores a reference to the Storage-object and will notify the storage if the list
    is empty. The storage will then remove the list.
    """
    def __init__(self, storage, aList=None):
        list.__init__(self, aList if aList is not None else [])
        self.storage = storage
    
    def __setitem__(self, key, value):
        list.__setitem__(self, key, value)
        
    def __delitem__(self, key):
        list.__delitem__(self, key)
        if len(self) == 0:
            self.storage._removeList(self)
            
    def remove(self, value):
        list.remove(self, value)
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
    def __init__(self, *args):
        if len(args) == 1 and type(args[0]) is dict:
            super().__init__()
            self.merge(args[0])
        else: super().__init__()
    
    def copy(self):
        """Return a copy of this storage-object containing copies of the original tag-value-lists."""
        result = Storage({tag: TagValueList(self, l) for tag, l in self.items()})
        for tagValueList in result.values():
            tagValueList.storage = result
        return result
        
    def __setitem__(self, key, value):
        if not isinstance(key, Tag):
            raise ValueError("key argument must be a tag instance. I got {}".format(key))
        if not isinstance(value, Sequence) or isinstance(value, str):
            raise ValueError("value must be a Sequence (but no string. I got {}".format(key))
            
        if len(value) == 0:
            if key in self:
                del self[key]
            else: pass # I won't save an empty list
        else: super().__setitem__(key, TagValueList(self, value))
    
    def _removeList(self, list):
        """Remove the given list from the values of this dict. This is called by the lists itself, when
        they become empty (see TagValueList)."""
        for key, value in self.items():
            if value == list:
                del self[key]
                return
                
    def add(self, tag, *values):
        """Add one or more values to the list of the given tag."""
        if not isinstance(tag, Tag):
            tag = get(tag)
        if tag not in self:
            self[tag] = values
        else: self[tag].extend(values)

    def addUnique(self, tag, *values):
        """Add one or more values to the list of the given tag. If a value is already contained in the list,
        do not add it again.
        """
        if not isinstance(tag, Tag):
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
                
    def remove(self, tag, *values):
        """Remove one or more values from the list of the given tag. If a value is not contained in this
        Storage just skip it.
        """
        if not isinstance(tag, Tag):
            tag = get(tag)
        for value in values:
            try:
                self[tag].remove(value)
            except ValueError: pass
            
    def replace(self, tag, oldValue, newValue):
        """Replace a value of *tag*. Because *newValue* will be at the same position where *oldValue* was,
        this might look nicer in displays, than simply removing *oldValue* and appending *newValue*.
        If *oldValue* is not present, add *newValue* anyway.
        """
        if not isinstance(tag, Tag):
            tag = get(tag)
        for i, value in enumerate(self[tag]):
            if value == oldValue:
                self[tag][i] = newValue
                return
        else: self.add(tag, newValue)
    
    def merge(self, other):
        """Add all tags from *other* to this storage. *other* may be another Storage-instance
        or a dict mapping tags to value-lists. This method won't add already existing values again.
        """
        for tag, valueList in other.items():
            self.addUnique(tag, *valueList)
                
    def removeTags(self, other):
        """Remove all values from *other* from this storage. *other* may be another Storage-instance
        or a dict mapping tags to value-lists. If *other* contains tags and values which are
        not contained in this storage, they will be skipped.
        """
        for tag, valueList in other.items():
            self.removeValues(tag, *valueList)

    def containsPrivateTags(self):
        """Return whether at least one tag in this object is private."""
        return any(tag.private for tag in self)
    
    def privateTags(self):
        """Return a Storage-object containing only the private tags of this object."""
        return Storage({tag: l for tag, l in self.items() if tag.private})
        
    def withoutPrivateTags(self, copy=False):
        """Return a Storage-object containing the same tags but without private tags. If there are no private
        tags and *copy* is False, return simply this object itself."""
        if copy or any(tag.private for tag in self):
            return Storage({tag: l for tag, l in self.items() if not tag.private})
        else: return self
        
    def getTuples(self):
        """Return a generator that yields the tags as (tag, value)-tuples.""" 
        for tag in self:
            for value in self[tag]:
                yield (tag, value)


class TagDifference:
    """Stores changes to tag-storages and provides methods to apply them.
    
        - *additions* is a list of (tag, value) pairs
        - *removals* is a list of (tag, value) pairs
        - *replacements* is a list of (tag, oldValue, newValue) tuples. This is used to replace
          values keeping the order.
    """
    def __init__(self, additions=None, removals=None, replacements=None):
        self.additions = additions
        self.removals = removals
        self.replacements = replacements
        
    def apply(self, element, withoutPrivateTags=False):
        """Change the tags of *element* (or anything that has a .tags attribute) according to this
        difference object. If *withoutPrivateTags* is True, ignore changes to private tags."""
        if self.removals is not None:
            for tag, value in self.removals:
                if tag in element.tags and not (withoutPrivateTags and tag.private):
                    if value in element.tags[tag]:
                        element.tags[tag].remove(value)
        
        if self.replacements is not None:
            for tag, value, newValue in self.replacements:
                if not (withoutPrivateTags and tag.private):
                    if tag in element.tags and value in element.tags[tag]: 
                        index = element.tags[tag].index(value)
                        element.tags[tag][index] = newValue
                    else: element.tags.add(tag, newValue)
        
        if self.additions is not None:
            for tag, value in self.additions:
                if not (withoutPrivateTags and tag.private):
                    element.tags.add(tag, value)
            
    def revert(self, element, withoutPrivateTags=False):
        """Undo the changes of this difference object to the tags of *element*.  If *withoutPrivateTags*
        is True, ignore changes to private tags."""
        if self.additions is not None:
            for tag, value in self.additions:
                if tag in element.tags and not (withoutPrivateTags and tag.private):
                    element.tags[tag].remove(value)
        
        if self.replacements is not None:
            for tag, value, newValue in self.replacements:
                if not (withoutPrivateTags and tag.private):
                    if tag in element.tags and newValue in element.tags[tag]:
                        index = element.tags[tag].index(newValue)
                        element.tags[tag][index] = value
                    else: element.tags.add(tag, value)
        
        if self.removals is not None:
            for tag, value in self.removals:
                if not (withoutPrivateTags and tag.private):
                    element.tags.add(tag, value)
            
    def getAdditions(self):
        """Return the list of (tag, value) pairs that are added by this TagDifference. This includes new
        values from the 'replacement' constructor parameter."""
        if self.replacements is not None:
            result = [(tag, newValue) for tag, _, newValue in self.replacements]
            if self.additions is not None:
                result.extend(self.additions)
            return result
        elif self.additions is not None:
            return self.additions
        else: return []
        
    def getRemovals(self):
        """Return the list of (tag, value) pairs that are removed by this TagDifference. This includes old
        values from the 'replacement' constructor parameter."""
        if self.replacements is not None:
            result = [(tag, oldValue) for tag, oldValue, _ in self.replacements]
            if self.removals is not None:
                result.extend(self.removals)
            return result
        elif self.removals is not None:
            return self.removals
        else: return []
        
    def inverse(self):
        """Return the inverse difference."""
        return utils.InverseDifference(self)
        
    def __str__(self):
        parts = []
        if self.additions is not None:
            parts.append("additions={}".format(self.additions))
        if self.removals is not None:
            parts.append("removals={}".format(self.removals))
        if self.replacements is not None:
            parts.append("replacements={}".format(self.replacements))
        return "{}({})".format(str(type(self)), ', '.join(parts))


class SingleTagDifference(TagDifference):
    """Convenience class that stores changes to a single tag type. *additions* and *removals* are simply
    lists of values, *replacements* is a list of (oldValue, newValue) pairs.
    """
    def __init__(self, tagType, additions=None, removals=None, replacements=None):
        if additions is not None:
            additions = [(tagType, value) for value in additions]
        if removals is not None:
            removals = [(tagType, value) for value in removals]
        if replacements is not None:
            replacements = [(tagType, oldValue, newValue) for oldValue, newValue in replacements]
        super().__init__(additions, removals, replacements)
                         
                         
class TagStorageDifference(TagDifference):
    """Subclass of TagDifference that simply takes two Storage-instances (old and new) and figures out
    additions/removals by itself."""
    def __init__(self, oldTags, newTags):
        # both arguments may be None
        self.oldTags = oldTags
        self.newTags = newTags
        
    def apply(self, element, withoutPrivateTags=False):
        # element may also be a FileBackend
        if self.newTags is None:
            element.tags = Storage()
        elif withoutPrivateTags:
            element.tags = self.newTags.withoutPrivateTags(copy=True)
        else: element.tags = self.newTags.copy()
        
    def revert(self, element, withoutPrivateTags=False):
        # element may also be a FileBackend
        if self.oldTags is None:
            element.tags = Storage()
        elif withoutPrivateTags:
            element.tags = self.oldTags.withoutPrivateTags(copy=True)
        else: element.tags = self.oldTags.copy()
        
    def getAdditions(self):
        if self.newTags is None:
            return []
        if self.oldTags is None:
            return [(tag, value) for tag, values in self.newTags.items() for value in values]
            pass
        result = []
        for newTag, newValues in self.newTags.items():
            oldValues = self.oldTags[newTag] if newTag in self.oldTags else []
            result.extend((newTag, value) for value in newValues if value not in oldValues)
        return result
    
    def getRemovals(self):
        if self.oldTags is None:
            return []
        if self.newTags is None:
            return [(tag, value) for tag, values in self.oldTags.items() for value in values]
        result = []
        for oldTag, oldValues in self.oldTags.items():
            newValues = self.newTags[oldTag] if oldTag in self.newTags else []
            result.extend((oldTag, value) for value in oldValues if value not in newValues)
        return result
    
    def __str__(self):
        return "TagStorageDifference(old={}, new={})".format(self.oldTags, self.newTags)
    
    
def findCommonTags(elements):
    """Returns a Storage object containing all tags that are equal in all of the elements."""
    commonTags = set(reduce(lambda x, y: x & y, [set(elem.tags.keys()) for elem in elements ]))
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


class TagDict(dict):
    """Ordered dictionary that accepts only tags as keys and will be sorted by their order."""
    def __setitem__(self, key, value):
        if not isinstance(key, Tag):
            raise ValueError("TagDict accepts only tags as keys. I got {}".format(key))
        super().__setitem__(key, value)
        
    def items(self):
        return utils.OrderedDictItems(self, self.keys())

    def keys(self):
        result = [tag for tag in tagList if tag in self]
        external = [tag for tag in super().keys() if not tag.isInDb()]
        external.sort(key=lambda tag: tag.name)
        result.extend(external)
        return result 
    
    def values(self):
        return utils.OrderedDictValues(self, self.keys())
    
    def __iter__(self):
        return self.keys()
