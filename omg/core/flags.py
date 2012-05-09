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

from PyQt4 import QtGui

from .. import application, constants, database as db, logging
from ..constants import ADDED, DELETED, CHANGED
from ..application import ChangeEvent


logger = logging.getLogger(__name__)
translate = QtGui.QApplication.translate

_flagsById = None
_flagsByName = None


def init():
    """Initialize the flag module loading flags from the database. You must call this method before methods
    like get can be used."""
    global _flagsById, _flagsByName, flagList
    _flagsById = {}
    _flagsByName = {}
    for row in db.query("SELECT id,name,icon FROM {}flag_names".format(db.prefix)):
        id,name,iconPath = row
        if db.isNull(iconPath):
            iconPath = None
        flagType = Flag(id,name,iconPath)
        _flagsById[flagType.id] = flagType
        _flagsByName[flagType.name] = flagType


class Flag:
    """A flagtype with an id, a name and optionally an icon. At first glance flags are like tags, but in fact
    they are much easier, because they have no values, valuetypes, translations and because they are not
    stored in files.
    
    Attributes of Flag: id, name, iconPath
    Read-only attribute: icon
    
    Usually you shold get flag instances via flags.get. The exception is for  flags that are not (yet) in
    the database (use :func:`exists` to check this). For these flags get will fail and you have to create
    your own instances. If you use the common instance, it will get automatically updated on
    FlagTypeChangeEvents.
    """
    def __init__(self,id=None,name=None,iconPath=None):
        self.id = id
        self.name = name
        self.iconPath = iconPath
        
    @property
    def iconPath(self):
        return self._iconPath

    @iconPath.setter
    def iconPath(self,iconPath):
        """Set the flag's iconPath and load the icon."""
        self._iconPath = iconPath
        if iconPath is not None:
            self.icon = QtGui.QIcon(iconPath)
        else: self.icon = None
        
    def __str__(self):
        return self.name
    
    def __eq__(self,other):
        return isinstance(other,Flag) and self.id == other.id
    
    def __ne__(self,other):
        return not isinstance(other,Flag) or self.id != other.id
    
    def __hash__(self):
        return self.id
        

def get(identifier):
    """Return a flagtype. *identifier* may be an int (the flag's id), a string (its name) or a flagtype (in
    this case it is simply returned)."""
    if isinstance(identifier,int):
        return _flagsById[identifier]
    elif isinstance(identifier,str):
        return _flagsByName[identifier]
    elif isinstance(identifier,FlagType):
        return identifier
    else: raise ValueError("identifier must be either int or string or FlagType.")


def exists(name):
    """Return whether a flagtype with the given name exists."""
    return name in _flagsByName


def isValidFlagname(name):
    """Return whether *name* is a valid name for a flagtype."""
    return 0 < len(name.encode()) <= constants.FLAG_VARCHAR_LENGTH and not name.isspace()


def allFlags():
    """Return a list containing all flags in the database."""
    return _flagsById.values()


class FlagTypeUndoCommand(QtGui.QUndoCommand):
    """This command adds, changes or deletes a flagtype. Which keyword arguments are necessary depends on the
    first parameter *action* which may be one of
    
        - constants.ADDED: In this case *data* must be a subset of the arguments of Flag.__init__ including
          'name' and excluding 'id' (the id is generated automatically by the database).
        - constants.CHANGED: This will change the flagType specified in the argument *flagType* according to
          the other arguments, which may be a subset of the arguments of Flag.__init__ except of 'id':
          
              FlagTypeUndoCommand(flagType=flagType,name='Great',iconPath=None)
              
        - constants.DELETED: A single argument *flagType*. The given flagType will be removed.
    """
    def __init__(self,action,flagType=None,**data):
        texts = {ADDED:   translate("FlagTypeUndoCommand","Add flagType"),
                 DELETED: translate("FlagTypeUndoCommand","Delete flagType"),
                 CHANGED: translate("FlagTypeUndoCommand","Change flagType")
                }
        super().__init__(texts[action])
        self.action = action
        if self.action == ADDED:
            self.addData = data
            self.flagType = None
        elif self.action == DELETED:
            self.flagType = flagType
        else:
            self.flagType = flagType
            self.oldData = {'name': flagType.name,'iconPath': flagType.iconPath}
            self.newData = data
        
    def redo(self):
        if self.action == ADDED:
            if self.flagType is None: # This is the first time this command is redone
                self.flagType = addFlagType(**self.addData)
                del self.addData
            else:
                # On subsequent redos ensure that the same object is recreated,
                # because it might be used in many elements within the undohistory.
                addFlagType(flagType=self.flagType)
        elif self.action == DELETED:
            removeFlagType(self.flagType)
        else: changeFlagType(self.flagType,**self.newData)

    def undo(self):
        if self.action == ADDED:
            removeFlagType(self.flagType)
        elif self.action == DELETED:
            # Ensure that the same object is recreated, because it might be used in many elements
            # within the undohistory.
            addFlagType(flagType=self.flagType)
        else: changeFlagType(self.flagType,**self.oldData)


class FlagTypeChangedEvent(ChangeEvent):
    """FlagTypeChangedEvent are used when a flagtype is added, changed or deleted."""
    def __init__(self,action,flagType):
        assert action in constants.CHANGE_TYPES
        self.action = action
        self.flagType = flagType


def addFlagType(**data):
    """Adds a new flagType to the database. The keyword arguments may contain either
    
        - a single argument 'flagType': In this case the given flagType is inserted into the database and
          some internal lists. Use this to undo a flagType's deletion.
        - a subset of the arguments of Flag.__init__. In this case this data is used to create a new flag.
          The subset must not contain 'id' and must contain at least 'name'.
          
    After creation the a FlagTypeChangedEvent is emitted.
    """
    if 'flagType' in data:
        flagType = data['flagType']
        data = (flagType.id,flagType.name,flagType.iconPath)
        db.query(
            "INSERT INTO {}flag_names (id,name,icon) VALUES (?,?,?)"
              .format(db.prefix),*data)
    else:
        # The difference to the if-part is that we have to get the id from the database
        flagType = Flag(**data)
        data = (flagType.name,flagType.iconPath)
        flagType.id = db.query(
            "INSERT INTO {}flag_names (name,icon) VALUES (?,?)"
              .format(db.prefix),*data).insertId()
    db.commit()
    logger.info("Added new flag '{}'".format(flagType.name))
    
    _flagsById[flagType.id] = flagType
    _flagsByName[flagType.name] = flagType
    application.dispatcher.changes.emit(FlagTypeChangedEvent(ADDED,flagType))
    return flagType


def removeFlagType(flagType):
    """Remove the given *flagType* from the database and emit a FlagTypeChangedEvent."""
    if not exists(flagType.name):
        raise ValueError("Cannot remove flagtype '{}' because it does not exist.".format(flagType))
    
    logger.info("Removing flag '{}'.".format(flagType))
    db.query("DELETE FROM {}flag_names WHERE id = ?".format(db.prefix),flagType.id)
    db.commit()
    del _flagsById[flagType.id]
    del _flagsByName[flagType.name]
    application.dispatcher.changes.emit(FlagTypeChangedEvent(DELETED,flagType))


def changeFlagType(flagType,**data):
    """Change the name and/or iconPath of *flagType* in the database and emit an event. The keyword arguments
    determine which properties should be changed::

        changeFlagType(flagType,name='Great',iconPath=None)
        
    Allowed keyword arguments are the arguments of Flag.__init__ except id.
    """
    # Below we will build a query like UPDATE flag_names SET ... using the list of assignments (e.g. (name=?).
    # The parameters will be sent with the query to replace the questionmarks.
    assignments = []
    params = []
    
    if 'name' in data:
        name = data['name']
        if name != flagType.name:
            if exists(name):
                raise ValueError("There is already a flag named '{}'.".format(name))
            logger.info("Changing flag name '{}' to '{}'.".format(flagType.name,name))
            assignments.append('name = ?')
            params.append(name)
            del _flagsByName[flagType.name]
            _flagsByName[name] = flagType
            flagType.name = name
        
    if 'iconPath' in data and data['iconPath'] != flagType.iconPath:
        assignments.append('icon = ?')
        params.append(data['iconPath'])
        flagType.iconPath = data['iconPath']
    
    if len(assignments) > 0:
        params.append(flagType.id) # for the where clause
        db.query("UPDATE {}flag_names SET {} WHERE id = ?".format(db.prefix,','.join(assignments)),*params)
        application.dispatcher.changes.emit(FlagTypeChangedEvent(CHANGED,flagType))
    db.commit()


class FlagDifference:
    """See tags.TagDifference"""
    
    def __init__(self, flagsA, flagsB):
        self.removals = set(flagsA) - set(flagsB)
        self.additions = set(flagsB) - set(flagsA)
        
    def apply(self, flagsA):
        for flag in self.removals:
            flagsA.remove(flag)
        flagsA.extend(self.additions)
        
    def revert(self, flagsB):
        for flag in self.additions:
            flagsB.remove(flag)
        flagsB.extend(self.removals)
        