# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
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

    * to manage tagtypes: convert tag-ids to tagnames and vice versa, add tagtypes to the database and remove
      them again, modify tagtypes (icon, title etc.)
    * to store tags in elements (or elsewhere)

There is one tagtype for each valid tagname. Some tagtypes are stored in the database and called 'internal'
while the other ones are called 'external'. Internal tags have an id, a type and may have a title, an icon
or be private (i.e. they will not be stored in files but only in the database).

For each tagtype there can be only one instance of Tag which is created in the init-method for internal tags
or when the get-method is invoked for the first time with the type's tagname. 

Call init at program start to initialize the module using the information in the tagids-table and use one of 
the following ways to get tags:

    * The easiest way is the get-method which takes a tag-id or a tag-name as parameter. Because you must
      never create your own Tag instances, this is the only method to get instances of external tags.
    * Use fromTitle to get tags from user input which may be in the user's language
      (e.g. ``'Künstler'``).
    * For some tags which have a special meaning to the program and cannot always be treated generically
      (e.g. the title-tag) there exist constants (e.g. TITLE). This allows to use tags.TITLE instead of
      tags.get(options.tags.title_tag). Do not use tags.get('title') as the user may decide to use another
      tagname than 'title' for his titles.
    * To iterate over all internal tags in the user-defined order use the module variable tagList.
    
\ """
from collections import Sequence
from functools import reduce

from PyQt4 import QtGui

from .. import application, config, constants, logging, utils
from ..constants import ADD, REMOVE, CHANGE, ADDED, REMOVED, CHANGED
from ..application import ChangeEvent

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


class TagValueError(ValueError):
    """This error is emitted by Tag.convertValue and ValueType.convertValue if a value cannot be converted
    into a different value-type."""
    pass


def init():
    """Initialize the variables of this module based on the information of the tagids-table and config-file.
    At program start or after changes of that table this method must be called to ensure the module has the
    correct tags and their IDs. Raise a RuntimeError when tags cannot be fetched from the database correctly.
    """
    global TITLE,ALBUM, db
    from omg import database as db
    
    if db.prefix+'tagids' not in db.listTables():
        logger.error("tagids-table is missing")
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
        result = db.query("SELECT id,tagname,tagtype,title,icon,private FROM {}tagids ORDER BY sort"
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
        newTag = Tag(tagName,id,valueType,title,iconPath,private)
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
    def __init__(self,name,description):
        self.name = name
        self.description = description

    @staticmethod
    def byName(name):
        """Given a type-name return the corresponding instance of this class."""
        for type in TYPES:
            if type.name == name:
                return type
        else: raise IndexError("There is no value type with name '{}'.".format(name))
        
    def isValid(self,value):
        """Return whether the given value is a valid tag-value for tags of this type."""
        if self.name == 'varchar':
            return isinstance(value,str) and 0 < len(value.encode()) <= constants.TAG_VARCHAR_LENGTH
        elif self.name == 'text':
            return isinstance(value,str) and len(value) > 0
        elif self.name == 'date':
            return isinstance(value,utils.FlexiDate)
        else: assert False

    def convertValue(self,value,crop=False,logCropping=True):
        """Convert *value* to this type and return the result. If conversion fails, raise a TagValueError.
        If *crop* is True, this method may crop *value* to make it valid (e.g. if *value* is too long for
        a varchar). If *logCropping* is True, cropping will print a logger warning.
        """
        if self.name == 'varchar':
            string = str(value)
            if len(string) == 0:
                raise TagValueError("varchar tags must have length > 0")
            if len(string.encode()) > constants.TAG_VARCHAR_LENGTH:
                if crop:
                    if logCropping:
                        logger.warning('Cropping a string that is too long for varchar tags: {}...'
                                       .format(string[:30]))
                    # Of course this might split in the middle of a unicode character. But errors='ignore'
                    # will silently remove the fragments 
                    encoded = string.encode()[:constants.TAG_VARCHAR_LENGTH]
                    return encoded.decode(errors='ignore')
                else: raise TagValueError("String is too long for a varchar tag: {}...".format(string[:30]))
            return string
        elif self.name == 'text':
            string = str(value)
            if len(string) > 0:
                return string
            else: raise TagValueError("text tags must have length > 0")
        elif self.name == 'date':
            if isinstance(value,utils.FlexiDate):
                return value
            else:
                string = str(value)
                try:
                    return utils.FlexiDate.strptime(string,crop,logCropping)
                except ValueError as e:
                    raise TagValueError(str(e))
        else: assert False

    def canConvert(self,value,crop=False):
        """Return whether *value* can be converted into this type using convertValue. For *crop* see
        convertValue.
        """
        try:
            self.convertValue(value,crop,logCropping=False)
        except TagValueError:
            return False
        else: return True

    def sqlFormat(self,value):
        """Convert *value* into a string that can be inserted into database queries."""
        if self.name == 'varchar':
            if len(value.encode()) > constants.TAG_VARCHAR_LENGTH:
                logger.error("Attempted to encode the following string for a varchar column although its "
                             "encoded size exceeds constants.TAG_VARCHAR_LENGTH. The string will be "
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
TYPE_VARCHAR = ValueType('varchar', translate("tags","Standard type for normal (not too long) text values"))
TYPE_TEXT = ValueType('text', translate("tags","Type for long texts (like e.g. lyrics)"))
TYPE_DATE = ValueType('date', translate("tags","Type for dates"))
TYPES = [TYPE_VARCHAR,TYPE_TEXT,TYPE_DATE]
    
    
class Tag:
    """
        A tagtype like 'artist'. 'title', etc.. Public attributes of tags are
        
            * id: The id of the tag. This is None for tags that are not in the database.
            * name: The name of the tag,
            * type: The value-type of this tag (e.g. varchar) as instance of ValueType,
            * title: A nice title to be displayed to the user (usually a translation of the name),
            * rawTitle: The title as set in the database. If a tag does not have a title set in the
              database this will be None, while 'title' will be the name. rawTitles must be unique (or None).
            * iconPath: Path to the tagtype's icon or None if if doesn't have an icon.
            * icon: A QIcon loaded from above path (read-only)
            * private: Whether the tag is private, i.e. stored only in the database and not in files.
            * isInDB: Whether the tag is contained in the database. Due to undo/redo oddities this is not
              equivalent to the tag having an id (add a tag to the db, press undo. The id will stay).
              The constructor assumes that for this moment isInDB and 'id is not None' are equivalent.

        You must use the get-method to get instances of this class. This method will ensure that there is
        always only one instance of a given tag and that this instance is updated automatically on
        TagTypeChangeEvents.
    """
    def __init__(self,name,id=None,type=None,title=None,iconPath=None,private=False):
        self.id = id
        self.name = name
        self.type = type
        self.rawTitle = title
        self.iconPath = iconPath # invoke iconPath.setter
        self.private = private
    
    def _getData(self):
        """Return some attributes as dict."""
        return {'id': self.id,
                'type':self.type,
                'title': self.rawTitle,
                'iconPath': self.iconPath,
                'private': self.private
                }
    
    def _setData(self,data):
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
        """Clear some attributes. This happens when adding a tagtype to the database is undone."""
        self.id,self.type,self.rawTitle,self.iconPath,self.private = None,None,None,None,False
    
    def isInDB(self):
        """Return whether this tagtype is internal, i.e. contained in the database."""
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
    def iconPath(self,iconPath):
        """Set the tag's iconPath and load the icon."""
        assert iconPath is None or isinstance(iconPath,str)
        self._iconPath = iconPath
        if iconPath is not None:
            self._icon = QtGui.QIcon(iconPath)
        else: self._icon = None
        
    def isValid(self,value):
        """Return whether the given value is a valid tag-value for this tag (this depends only on the
        tag-type).
        """
        if self.type is not None:
            return self.type.isValid(value)
        else: return True

    def convertValue(self,value,crop=False,logCropping=True):
        """Convert a value to this tagtype. Raise a TagValueError if conversion is not possible.
        If *crop* is True, this method may crop *value* to make it valid (e.g. if *value* is too long for
        a varchar). If *logCropping* is True, cropping will print a logger warning.
        """
        if self.type is None:
            return str(value)
        else: return self.type.convertValue(value,crop)
    
    def canConvert(self,value,crop=False):
        """Return whether *value* can be converted into this type using convertValue. For *crop* see
        convertValue.
        """
        try:
            self.convertValue(value,crop,logCropping=False)
        except TagValueError:
            return False
        else: return True
        
    def fileFormat(self, string):
        """Format a value suitable for writing to a file."""
        if self.type is not None:
            return self.type.fileFormat(string)
        return string
    
    def sqlFormat(self,value):
        """Convert *value* into a string that can be inserted into database queries."""
        if self.type is None:
            raise ValueError("sqlFormat can only be used with internal tags.")
        return self.type.sqlFormat(value)

    def __repr__(self):
        return '"{0}"'.format(self.name)

    def __str__(self):
        return self.title


def isValidTagName(name):
    """Return whether *name* is a valid tag name. OMG uses the restrictions imposed by the
    Vorbis-specification: ASCII 0x20 through 0x7D, 0x3D ('=') excluded.
    Confer http://xiph.org/vorbis/doc/v-comment.html.
    """
    try:
        encoded = name.encode('ascii')
        return 0 < len(encoded) < 64 and all(0x20 <= c <= 0x7D and c != 0x3D for c in encoded)
    except UnicodeEncodeError:
        return False


def isInDB(name):
    """Return whether a tag with the given name exists in the database."""
    return name in _tagsByName and _tagsByName[name].isInDB()


def get(identifier,addDialogIfNew=False):
    """Return the tag identified by *identifier*:
    
        If *identifier* is an integer return the tag with this id.
        If *identifier* is a string return the tag with this name. 
        If *identifier* is a Tag-instance, return *identifier*.
        
    This method does never create a second instance of one tag.
    """
    if isinstance(identifier,int):
        return _tagsById[identifier]
    elif isinstance(identifier,str):
        identifier = identifier.lower()
        if identifier in _tagsByName:
            return _tagsByName[identifier]
        else:
            if not isValidTagName(identifier):
                raise ValueError("'{}' is not a valid tagname".format(identifier))
            newTag = Tag(identifier)
            _tagsByName[identifier] = newTag
            if addDialogIfNew:
                from .gui.tagwidgets import NewTagTypeDialog
                NewTagTypeDialog.addTagType(newTag)
            return newTag
    elif isinstance(identifier, Tag):
        return identifier
    else:
        raise TypeError("Identifier's type is neither int nor string nor tag: {} of type {}"
                            .format(identifier,type(identifier)))


def isTitle(title):
    """Return whether *title* is the raw title of a tag (comparison is case-insensitive!)."""
    return title.lower() in (str.lower(tag.rawTitle) for tag in tagList if tag.rawTitle is not None)


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

    
def addTagType(tagType,type,**data):
    """Add a tagtype to the database. *tagType* can be a valid tagname or an external tagtype. Using keyword
    arguments you can optionally set attributes of the tagtype which external tagtypes don't have
    Allowed keys are
        title, iconPath, private and index (the index of the tagtype within tags.tagList).
        
    If the type cannot be added because an element contains a value which is invalid for the chosen type,
    a TagValueError is raised.
    """
    if isinstance(tagType,str):
        tagType = get(tagType)
    if tagType.isInDB():
        raise ValueError("Cannot add tag '{}' because it is already in the DB.".format(tagType))
    if 'title' in data:
        if data['title'] is not None and isTitle(data['title']):
            raise ValueError("Cannot add tag '{}' with title '{}' because that title exists already."
                             .format(tagType,data['title']))
            
    application.stack.beginMacro(translate("TagTypeUndoCommand","Add tagtype to DB"))
    try:
        _convertTagTypeOnLevels(tagType,type)
    except TagValueError as error:
        application.stack.endMacro()
        #TODO: remove macro from stack
        raise error

    data['type'] = type
    application.stack.push(TagTypeUndoCommand(ADD,tagType,**data))
    application.stack.endMacro()
    
    return tagType
        
    
def _addTagType(tagType,**data):
    """Similar to addTagType, but not undoable. *tagType* must be an external Tag instance. Its value-type
    must be given as keyword-argument 'type'."""
    assert tagType.name in _tagsByName # if the tag was created with get, it is already contained there
    assert 'type' in data
    
    if 'index' in data:
        index = data['index']
    else: index = len(tagList)   
    
    db.query("UPDATE {}tagids SET sort=sort+1 WHERE sort >= ?".format(db.prefix),index)
 
    tagType._setData(data)
    tagList.insert(index,tagType)
    
    if tagType.id is not None: # id has been set in _setData
        data = (tagType.id,tagType.name,tagType.type.name,tagType.rawTitle,
                tagType.iconPath,tagType.private,index)
        db.query(
            "INSERT INTO {}tagids (id,tagname,tagtype,title,icon,private,sort) VALUES (?,?,?,?,?,?,?)"
              .format(db.prefix),*data)
    else:
        # The difference to the if-part is that we have to get the id from the database
        data = (tagType.name,tagType.type.name,tagType.rawTitle,tagType.iconPath,tagType.private,index)
        tagType.id = db.query(
            "INSERT INTO {}tagids (tagname,tagtype,title,icon,private,sort) VALUES (?,?,?,?,?,?)"
              .format(db.prefix),*data).insertId()
    logger.info("Added new tag '{}' of type '{}'.".format(tagType.name,tagType.type.name))

    _tagsById[tagType.id] = tagType
    application.dispatcher.emit(TagTypeChangedEvent(ADDED,tagType))
    return tagType
    

def removeTagType(tagType):
    """Remove a tagtype from the database. The tagtype must not be contained in any internal elements!
    """
    if not tagType.isInDB():
        raise ValueError("Cannot remove external tagtype '{}' from DB.".format(tagType))
    if tagType in (TITLE,ALBUM):
        raise ValueError("Cannot remove title or album tag.")
    if db.query("SELECT COUNT(*) FROM {}tags WHERE tag_id = ?".format(db.prefix),tagType.id).getSingle() > 0:
        raise ValueError("Cannot remove a tag that appears in internal elements.")
    
    application.stack.beginMacro(translate("TagTypeUndoCommand","Remove tagtype from DB"))
    try:
        _convertTagTypeOnLevels(tagType,None)
    except TagValueError as error:
        application.stack.endMacro()
        #TODO: remove macro from stack
        raise error
    application.stack.push(TagTypeUndoCommand(REMOVE,tagType))
    application.stack.endMacro()
    
    
def _removeTagType(tagType):
    """Like removeTagType, but not undoable: Remove a tagtype from the database, including all its values
    and relations. This will not touch any files though!
    """
    logger.info("Removing tag '{}'.".format(tagType.name))
    db.query("DELETE FROM {}tagids WHERE id=?".format(db.prefix),tagType.id)
    db.query("UPDATE {}tagids SET sort=sort-1 WHERE sort > ?".format(db.prefix),tagList.index(tagType))
    del _tagsById[tagType.id]
    tagList.remove(tagType)
    tagType._clearData()
    application.dispatcher.emit(TagTypeChangedEvent(REMOVED,tagType))
    

def changeTagType(tagType,**data):
    """Change an internal tagtype. In particular update the single instance *tagType* and the database.
    The keyword arguments determine which properties should be changed::

        changeTagType(tagType,title='Artist',iconPath=None)
        
    Allowed keyword arguments are type, title, iconPath, private. If the type or private is changed,
    the tagtype must not appear in any internal elements.
    If the type cannot be changed because an (external) element contains a value which is invalid for the new
    type, a TagValueError is raised.
    """
    if not tagType.isInDB():
        raise ValueError("Cannot change an external tagtype '{}'.".format(tagType))
    if ('type' in data and data['type'] != tagType.type) \
            or ('private' in data and data['private'] != tagType.private):
        count = db.query("SELECT COUNT(*) FROM {}tags WHERE tag_id = ?"
                         .format(db.prefix),tagType.id).getSingle()
        if count > 0:
            raise ValueError("Cannot change the type of a tag that appears in internal elements.")
    
    application.stack.beginMacro(translate("TagTypeUndoCommand","Change tagtype"))
    if 'type' in data and data['type'] != tagType.type:
        try:
            _convertTagTypeOnLevels(tagType,data['type'])
        except TagValueError as error:
            application.stack.endMacro()
            #TODO: remove macro from stack
            raise error
        
    application.stack.push(TagTypeUndoCommand(CHANGE,tagType,**data))
    application.stack.endMacro()
    
    
def _changeTagType(tagType,**data):
    """Like changeTagType, but not undoable."""
    assert tagType.isInDB()
    
    # Below we will build a query like UPDATE tagids SET ... using the list of assignments (e.g. tagtype=?).
    # The parameters will be sent with the query to replace the question marks.
    assignments = []
    params = []
    
    if 'type' in data and data['type'] != tagType.type:
        type = data['type']
        if not isinstance(type,ValueType):
            raise ValueError("'{}' is not a ValueType.".format(type))
        logger.info("Changing type of tag '{}' from '{}' to '{}'."
                    .format(tagType.name,tagType.type.name,type.name))
        assignments.append('tagtype = ?')
        params.append(type.name)
        tagType.type = type
    
    if 'title' in data and data['title'] != tagType.rawTitle:
        title = data['title']
        if title is not None and len(title) == 0:
            title = None
        assert title is None or not isTitle(title) # titles must be unique
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
        db.query("UPDATE {}tagids SET {} WHERE id = ?"
                    .format(db.prefix,','.join(assignments)),*params)
        application.dispatcher.emit(TagTypeChangedEvent(CHANGED,tagType))


def _convertTagTypeOnLevels(tagType,valueType):
    """Convert all occurences of *tagType* on all levels from *tagType*'s value-type to *valueType*.
    This method is used to adjust levels just before a tag-type's value-type changes. *valueType* may be
    None, indicating that *tagType* is going to become an external tag.
    Before any level is changed this method checks whether all values can be converted. If not, a
    TagValueError is raised.
    """
    from . import levels, commands
    cmds = []
    for level in levels.allLevels:
        diffs = {}
        for element in level.elements.values(): # only external elements possible => won't take too long
            if tagType in element.tags:
                if valueType is not None:
                    newValues = [valueType.convertValue(value) for value in element.tags[tagType]]
                else: newValues = [str(value) for value in element.tags[tagType]]
                diff = TagDifference.singleTagDifference(tagType,element.tags[tagType],newValues)
                if diff is not None:
                    diffs[element] = diff
        if len(diffs) > 0:
            cmds.append(commands.ChangeTagsCommand(level,diffs))
    # Only start changing levels if all tag value conversions have been successful.
    for command in cmds:
        application.stack.push(command)
        
        
class TagTypeUndoCommand(QtGui.QUndoCommand):
    """This command adds, changes or removes a tagtype. Which keyword arguments are necessary depends on the
    first parameter *action*. Use the methods addTagType, removeTagType and changeTagTyp instead of using
    this command directly.
    """
    def __init__(self,action,tagType,**data):
        texts = {ADD:   translate("TagTypeUndoCommand","Add tagtype to DB"),
                 REMOVE: translate("TagTypeUndoCommand","Remove tagtype from DB"),
                 CHANGE: translate("TagTypeUndoCommand","Change tagtype")
                }
        super().__init__(texts[action])
        self.action = action
        if self.action == ADD:
            self.tagType = tagType
            self.data = data
        elif self.action == REMOVE:
            self.tagType = tagType
            self.data = tagType._getData()
            self.data['index'] = tagList.index(tagType)
        else:
            self.tagType = tagType
            self.oldData = tagType._getData()
            self.newData = data
        
    def redo(self):
        if self.action == ADD:
            _addTagType(self.tagType,**self.data)
        elif self.action == REMOVE:
            _removeTagType(self.tagType)
        else: _changeTagType(self.tagType,**self.newData)

    def undo(self):
        if self.action == ADD:
            _removeTagType(self.tagType)
        elif self.action == REMOVE:
            # Ensure that the same object is recreated, because it might be used in many elements
            # within the undohistory.
            _addTagType(self.tagType,**self.data)
        else: _changeTagType(self.tagType,**self.oldData)


class TagTypeChangedEvent(ChangeEvent):
    """TagTypeChangedEvents are used when a tagtype (like artist, composer...) is added, changed or removed.
    """
    def __init__(self,action,tagType):
        assert action in constants.CHANGE_TYPES
        self.action = action
        self.tagType = tagType
  
    
def moveTagType(tagType,newIndex):
    """Move *tagType* to the given index within tagList."""
    index = tagList.index(tagType)
    if index == newIndex:
        return
    newList = tagList[:]
    del newList[index]
    newList.insert(newIndex,tagType)
    application.stack.push(TagTypeOrderUndoCommand(newList))
    
    
def moveTagTypes(newList):
    """Replace tagList by *newList*. Both lists must contain the same tagtypes!."""
    application.stack.push(TagTypeOrderUndoCommand(newList))


def _moveTagTypes(newList):
    """Like moveTagTypes, but not undoable.""" 
    global tagList
    if set(tagList) != set(newList):
        raise ValueError("*newList* must contain the same tags as tags.tagList")
    db.multiQuery("UPDATE {}tagids SET sort = ? WHERE id = ?".format(db.prefix),
                  enumerate([t.id for t in newList]))
    tagList = newList
    application.dispatcher.emit(TagTypeOrderChangeEvent())
    
    
class TagTypeOrderUndoCommand(QtGui.QUndoCommand):
    """Command that changes the order of the tagtypes. *newList* specifies the new order and will be used
    as replacement for tags.tagList. *newList* must contain the same tagtypes as tags.tagList.
    
    Note that TagTypeOrderUndoCommand does not guarantee that the sort numbers in the database will be
    restored exactly when the command is undone. They will be set to values such that the order of
    tags.tagList is restored.
    """ 
    def __init__(self,newList):
        super().__init__(translate("TagTypeOrderUndoCommand","Change tagtype order"))
        self.oldList = tagList
        self.newList = newList
    
    def redo(self):
        _moveTagTypes(self.newList)
    
    def undo(self):
        _moveTagTypes(self.oldList)
        

class TagTypeOrderChangeEvent(ChangeEvent):
    """This event is emitted when the order of tagtypes has changed. The order is always stored in
    tags.tagList."""
    pass


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
        if len(args) == 1 and type(args[0]) is dict:
            dict.__init__(self)
            self.merge(args[0])
        else:
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
        If *oldValue* is not present, add *newValue* anyway.
        """
        if not isinstance(tag,Tag):
            tag = get(tag)
        for i,value in enumerate(self[tag]):
            if value == oldValue:
                self[tag][i] = newValue
                return
        else: self.add(tag,newValue)
    
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


class TagDifference:
    """A class storing the difference between two Storage() objects, for use in UndoCommands."""
    def __init__(self, tagsA, tagsB):
        self.removals = []
        self.additions = []
        if tagsA is None:
            tagsA = {}
        if tagsB is None:
            tagsB = {}
        for tag, valuesA in tagsA.items():
            if tag not in tagsB:
                self.removals.append((tag, valuesA[:]))
            else:
                valuesB = tagsB[tag]
                removedValues = [v for v in valuesA if v not in valuesB]
                if len(removedValues) > 0:
                    self.removals.append((tag, removedValues))
                newValues = [v for v in valuesB if v not in valuesA]
                if len(newValues) > 0:
                    self.additions.append((tag, newValues))
        for tag, valuesB in tagsB.items():
            if tag not in tagsA:
                self.additions.append((tag, valuesB[:]))

    def inverse(self):
        """Return the "inverse" difference object with additions and removals exchanged."""
        ret = TagDifference(None, None)
        ret.additions = self.removals[:]
        ret.removals = self.additions[:]
        return ret
    
    def __str__(self):
        return "{}(additions={}, removals={})".format(str(type(self)), self.additions, self.removals)
    
    def onlyPrivateChanges(self):
        return all(tag.private for (tag, _) in self.additions) and \
               all(tag.private for (tag, _) in self.removals)
               
    def apply(self, tagsA, includePrivate=True):
        """Apply the changes to *tagsA*, transforming them into *tagsB* given to the constructor."""
        for tag, values in self.removals:
            if includePrivate or not tag.private:
                tagsA.remove(tag, *values)
        for tag, values in self.additions:
            if includePrivate or not tag.private:
                tagsA.add(tag, *values)
            
    def revert(self, tagsB, includePrivate=True):
        """Revert the changes from *tagsB*, transforming them into *tagsA* as given to the constructor."""
        for tag, values in self.additions:
            if includePrivate or not tag.private:
                tagsB.remove(tag, *values)
        for tag, values in self.removals:
            if includePrivate or not tag.private:
                tagsB.add(tag, *values)

    @staticmethod
    def singleTagDifference(tagType,oldValues,newValues):
        result = TagDifference(None,None)
        result.additions = [(tagType,[value for value in newValues if value not in oldValues])]
        result.removals = [(tagType,[value for value in oldValues if value not in newValues])]
        
        if len(result.additions) > 0 or len(result.removals) > 0:
            return result
        else: return None
        

def findCommonTags(elements):
    """Returns a Storage object containing all tags that are equal in all of the elements.
    """
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


class TagDict(dict):
    """Ordered dictionary that accepts only tags as keys and will be sorted by their order."""
    def __setitem__(self,key,value):
        if not isinstance(key,Tag):
            raise ValueError("TagDict accepts only tags as keys. I got {}".format(key))
        super().__setitem__(key,value)
        
    def items(self):
        return utils.OrderedDictItems(self,self.keys())

    def keys(self):
        result = [tag for tag in tagList if tag in self]
        external = [tag for tag in super().keys() if not tag.isInDB()]
        external.sort(key=lambda tag: tag.name)
        result.extend(external)
        return result 
    
    def values(self):
        return utils.OrderedDictValues(self,self.keys())
    
    def __iter__(self):
        return self.keys()
         
