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

from PyQt4 import QtGui

from .. import application, config, constants, logging, utils
from ..constants import ADDED, DELETED, CHANGED
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
        
    def isValid(self,value):
        """Return whether the given value is a valid tag-value for tags of this type."""
        if self.name == 'varchar':
            return isinstance(value,str) and 0 < len(value.encode()) <= constants.TAG_VARCHAR_LENGTH
        elif self.name == 'text':
            return isinstance(value,str) and len(value) > 0
        elif self.name == 'date':
            if isinstance(value,utils.FlexiDate):
                return True
            else:
                try: 
                    utils.FlexiDate.strptime(value)
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
            convertedValue = utils.FlexiDate.strptime(value)
        else: convertedValue = value # nothing to convert
        if newType.isValid(convertedValue):
            return convertedValue
        else: raise ValueError("Converted value {} is not valid for valuetype {}."
                                 .format(convertedValue,newType))

    def sqlFormat(self,value):
        """Convert *value* into a string that can be inserted into database queries."""
        if self.name == 'date':
            if isinstance(value,utils.FlexiDate):
                return value.sqlFormat()
            else: return utils.FlexiDate.strptime(value).sqlFormat()
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
            return utils.FlexiDate.strptime(string)
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
        A tagtype like 'artist'. 'title', etc.. Public attributes of tags are
        
            * id: The id of the tag if it is in the database or None otherwise,
            * name: The name of the tag,
            * type: The value-type of this tag (e.g. varchar) as instance of :class:`omg.tags.ValueType`,
            * title: A nice title to be displayed to the user (usually a translation of the name),
            * rawTitle: The title as set in the database. If a tag does not have a title set in the
              database this will be None, while 'title' will be the name.
            * iconPath: Path to the tagtype's icon or None if if doesn't have an icon.
            * icon: A QIcon loaded from above path (read-only)
            * private: Whether the flag is private, i.e. stored only in the database and not in files.

        Usually you should get tag instances via the :func:`get-method<omg.tags.get>`. The exception is for
        tags that are not (yet) in the database (use :func:`exists` to check this). For these tags
        :func:`get` will fail and you have to create your own instances. If you use the common instance, it
        will get automatically updated on TagTypeChangeEvents.
    """
    def __init__(self,id=None,name=None,type=None,title=None,iconPath=None,private=None):
        self.id = id
        if name is not None:
            assert isValidTagname(name)
        self.name = name
        self.type = type
        if title is not None and title != self.name:
            self.rawTitle = title
        else: self.rawTitle = None
        self.iconPath = iconPath
        self.private = private
        
    @property
    def iconPath(self):
        return self._iconPath

    @iconPath.setter
    def iconPath(self,iconPath):
        """Set the tag's iconPath and load the icon."""
        assert iconPath is None or isinstance(iconPath,str)
        self._iconPath = iconPath
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
    
    @property
    def title(self):
        return self.rawTitle if self.rawTitle is not None else self.name
    
    @title.setter
    def title(self,title):
        if title != '' and title != self.name:
            self.rawTitle = title
        else: self.rawTitle = None

        
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


class TagTypeUndoCommand(QtGui.QUndoCommand):
    """This command adds, changes or deletes a tagtype. Which keyword arguments are necessary depends on the
    first parameter *action* which may be one of
    
        - constants.ADDED: In this case *data* must be a subset of the arguments of Tag.__init__ including
          'name' and 'type' and excluding 'id' (the id is generated automatically by the database).
        - constants.CHANGED: This will change the tagtype specified in the argument *tagType* according to
          the other arguments, which may be a subset of the arguments of Tag.__init__ except of 'id':
          
              TagTypeUndoCommand(tagType=tagType,name='artist',iconPath=None)
              
        - constants.DELETED: A single argument *tagType*. The given tagtype will be removed.
    """
    def __init__(self,action,tagType=None,**data):
        texts = {ADDED:   translate("TagTypeUndoCommand","Add tagtype"),
                 DELETED: translate("TagTypeUndoCommand","Delete tagtype"),
                 CHANGED: translate("TagTypeUndoCommand","Change tagtype")
                }
        super().__init__(texts[action])
        self.action = action
        if self.action == ADDED:
            self.addData = data
            self.tagType = None
        elif self.action == DELETED:
            self.tagType = tagType
        else:
            self.tagType = tagType
            self.oldData = {'name': tagType.name,'type': tagType.type,'title': tagType.title,
                            'iconPath': tagType.iconPath, 'private': tagType.private }
            self.newData = data
        
    def redo(self):
        if self.action == ADDED:
            if self.tagType is None: # This is the first time this command is redone
                self.tagType = addTagType(**self.addData)
                del self.addData
            else:
                # On subsequent redos ensure that the same object is recreated,
                # because it might be used in many elements within the undohistory.
                addTagType(tagType=self.tagType)
        elif self.action == DELETED:
            removeTagType(self.tagType)
        else: changeTagType(self.tagType,**self.newData)

    def undo(self):
        if self.action == ADDED:
            removeTagType(self.tagType)
        elif self.action == DELETED:
            # Ensure that the same object is recreated, because it might be used in many elements
            # within the undohistory.
            addTagType(tagType=self.tagType)
        else: changeTagType(self.tagType,**self.oldData)


class TagTypeChangedEvent(ChangeEvent):
    """TagTypeChangedEvents are used when a tagtype (like artist, composer...) is added, changed or deleted.
    """
    def __init__(self,action,tagType):
        assert action in constants.CHANGE_TYPES
        self.action = action
        self.tagType = tagType
        
        
def addTagType(**data):
    """Adds a new tagtype to the database. The keyword arguments may contain either
    
        - a single argument 'tagType': In this case the given tagType is inserted into the database and some
          internal lists. Use this to undo a tagtype's deletion.
        - a subset of the arguments of Tag.__init__. In this case this data is used to create a new tag.
          The subset must not contain 'id' and must contain at least 'name' and 'type'.
          
    After creation a TagTypeChangedEvent is emitted.
    """
    from . import database as db
    if 'tagType' in data:
        tagType = data['tagType']
        data = (tagType.id,tagType.name,tagType.type.name,tagType.title,tagType.iconPath,tagType.private)
        db.query(
            "INSERT INTO {}tagids (id,tagname,tagtype,title,icon,private) VALUES (?,?,?,?,?,?)"
              .format(db.prefix),*data)
    else:
        # The difference to the if-part is that we have to get the id from the database
        tagType = Tag(**data)
        data = (tagType.name,tagType.type.name,tagType.title,tagType.iconPath,tagType.private)
        tagType.id = db.query(
            "INSERT INTO {}tagids (tagname,tagtype,title,icon,private) VALUES (?,?,?,?,?)"
              .format(db.prefix),*data).insertId()
    db.commit()
    logger.info("Added new tag '{}' of type '{}'.".format(tagType.name,tagType.type.name))
    _tagsByName[tagType.name] = tagType
    _tagsById[tagType.id] = tagType
    tagList.append(tagType)
    application.dispatcher.changes.emit(TagTypeChangedEvent(ADDED,tagType))
    return tagType
        

def removeTagType(tagType):
    """Remove a tagtype from the database, including all its values and relations. This will not touch any
    files though!
    After removal a TagTypeChangedEvent is emitted.
    """
    logger.info("Removing tag '{}'.".format(tagType.name))
    if tagType == TITLE or tagType == ALBUM:
        raise ValueError("Cannot remove title or album tag.")
    
    from . import database as db
    db.query("DELETE FROM {}tagids WHERE id=?".format(db.prefix),tagType.id)
    db.commit()
    del _tagsByName[tagType.name]
    del _tagsById[tagType.id]
    tagList.remove(tagType)
    application.dispatcher.changes.emit(TagTypeChangedEvent(DELETED,tagType))


def changeTagType(tagType,**data):
    """Change a tagtype. In particular update the instance *tagType* (this is usually the only instance of
    this tag) and the database. The keyword arguments determine which properties should be changed::

        changeTagType(tagType,name='artist',iconPath=None)
        
    Allowed keyword arguments are the arguments of Tag.__init__ except id.
    After the change a TagTypeChangedEvent is emitted.
    """
    # Below we will build a query like UPDATE tagids SET ... using the list of assignments (e.g. (tagname=?).
    # The parameters will be sent with the query to replace the questionmarks.
    assignments = []
    params = []
    
    if 'name' in data:
        name = data['name'].lower()
        if not isValidTagname(name):
            raise ValueError("'{}' is not a valid tagname.".format(name))
        if name != tagType.name:
            logger.info("Changing tag '{}' to '{}'.".format(tagType.name,name))
            assignments.append('tagname = ?')
            params.append(name)
            del _tagsByName[tagType.name]
            _tagsByName[name] = tagType
            tagType.name = name
    
    if 'type' in data and data['type'] != tagType.type:
        type = data['type']
        if not isinstance(type,ValueType):
            raise ValueError("'{}' is not a ValueType.".format(type))
        logger.info("Changing type of tag '{}' from '{}' to '{}'."
                    .format(tagType.name,tagType.type.name,type.name))
        assignments.append('tagtype = ?')
        params.append(type.name)
        tagType.type = type
    
    if 'title' in data and data['title'] != tagType.title:
        assignments.append('title = ?')
        params.append(data['title'])
        tagType.title = data['title'] 
        
    if 'iconPath' in data and data['iconPath'] != tagType.iconPath:
        assignments.append('icon = ?')
        params.append(data['iconPath'])
        tagType.iconPath = data['iconPath']
        
    if 'private' in data and bool(data['private']) != tagType.private:
        assignments.append('private = 1' if data['private'] else 'private = 0')
        tagType.private = bool(data['private'])
    
    if len(assignments) > 0:
        params.append(tagType.id) # for the where clause
        from . import database as db
        db.query("UPDATE {}tagids SET {} WHERE id = ?"
                    .format(db.prefix,','.join(assignments)),*params)
        db.commit()
        application.dispatcher.changes.emit(TagTypeChangedEvent(CHANGED,tagType))


def loadTagTypesFromDB():
    """Initialize _tagsById, _tagsByName and tagList from the database. Raise a runtime error when the 
    tags cannot be fetched from the database (e.g. because the tagids table is missing)."""
    global _tagsByName, _tagsById, tagList
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
    global TITLE,ALBUM, db
    from omg import database as db
    
    if db.prefix+'tagids' not in db.listTables():
        logger.error("tagids-table is missing")
        raise RuntimeError()
    
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
            tagsA = Storage()
        if tagsB is None:
            tagsB = Storage()
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
                
    def onlyPrivateChanges(self):
        return all(tag.private for (tag, _) in self.additions) and \
               all(tag.private for (tag, _) in self.removals)
               
    def apply(self, tagsA, includePrivate = True):
        """Apply the changes to *tagsA*, transforming them into *tagsB* given to the constructor."""
        for tag, values in self.removals:
            if includePrivate or not tag.private:
                tagsA.remove(tag, *values)
        for tag, values in self.additions:
            if includePrivate or not tag.private:
                tagsA.add(tag, *values)
            
    def revert(self, tagsB, includePrivate = True):
        """Revert the changes from *tagsB*, transforming them into *tagsA* as given to the constructor."""
        for tag, values in self.additions:
            if includePrivate or not tag.private:
                tagsB.remove(tag, *values)
        for tag, values in self.removals:
            if includePrivate or not tag.private:
                tagsB.add(tag, *values)
    
    def __str__(self):
        return "TagDifference(additions={}, removals={})".format(self.additions, self.removals)
                 

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
