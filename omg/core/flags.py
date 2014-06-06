# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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

from .. import application, constants, database as db, logging, utils, stack
from ..constants import ADDED, DELETED, CHANGED
from ..application import ChangeEvent

translate = QtGui.QApplication.translate

_flagsById = None
_flagsByName = None


# This separator is used to separate flag names from each other. It must not be part of a flag name.
FLAG_SEPARATOR = '|'


def init():
    """Initialize the flag module loading flags from the database. You must call this method before methods
    like 'get' can be used."""
    global _flagsById, _flagsByName
    _flagsById = {}
    _flagsByName = {}
    for row in db.query("SELECT id, name, icon FROM {p}flag_names"):
        id, name, iconPath = row
        if db.isNull(iconPath):
            iconPath = None
        flagType = Flag(id, name, iconPath)
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
    def __init__(self, id=None, name=None, iconPath=None):
        self.id = id
        self.name = name
        self.iconPath = iconPath
        
    @property
    def iconPath(self):
        return self._iconPath

    @iconPath.setter
    def iconPath(self, iconPath):
        """Set the flag's iconPath and load the icon."""
        self._iconPath = iconPath
        if iconPath is not None:
            self.icon = QtGui.QIcon(iconPath)
        else: self.icon = None
        
    def __repr__(self):
        return self.name
    
    def __eq__(self, other):
        return isinstance(other, Flag) and self.id == other.id
    
    def __ne__(self, other):
        return not isinstance(other, Flag) or self.id != other.id
    
    def __hash__(self):
        return self.id
        

def get(identifier):
    """Return a flagtype. *identifier* may be an int (the flag's id), a string (its name) or a flagtype (in
    this case it is simply returned)."""
    if isinstance(identifier, int):
        return _flagsById[identifier]
    elif isinstance(identifier, str):
        return _flagsByName[identifier]
    elif isinstance(identifier, Flag):
        return identifier
    else: raise ValueError("identifier must be either int or string or FlagType.")


def exists(name):
    """Return whether a flagtype with the given name exists."""
    return name in _flagsByName


def isValidFlagname(name):
    """Return whether *name* is a valid name for a flagtype."""
    return 0 < len(name.encode()) <= constants.FLAG_VARCHAR_LENGTH \
                and not name.isspace() and FLAG_SEPARATOR not in name 


def allFlags():
    """Return a list containing all flags in the database."""
    return _flagsById.values()


def addFlagType(name, **data):
    """Add a new flagtype with the given name to the database. *data* may be used to set attributes. 
    Currently only 'iconPath' is supported. Return the new flag type."""
    if exists(name):
        raise ValueError("There is already a flag with name '{}'.".format(name))
    if not isValidFlagname(name):
        raise ValueError("'{}' is not a valid flagname.".format(name))
    flagType = Flag(name=name, **data)
    stack.push(translate("Flags", "Add flag type"),
               stack.Call(_addFlagType, flagType),
               stack.Call(_deleteFlagType, flagType))
    return flagType
    
    
def _addFlagType(flagType):
    """Add a flagType to database and some internal lists and emit a FlagTypeChanged-event. If *flagType*
    doesn't have an id, choose an unused one.
    """
    flagType.id = db.query("INSERT INTO {p}flag_names (name, icon) VALUES (?,?)",
                           flagType.name, flagType.iconPath).insertId()
    logging.info(__name__, "Added new flag '{}'".format(flagType.name))
    
    _flagsById[flagType.id] = flagType
    _flagsByName[flagType.name] = flagType
    application.dispatcher.emit(FlagTypeChangedEvent(ADDED, flagType))


def deleteFlagType(flagType):
    """Delete a flagtype from all elements and the database."""
    stack.beginMacro(translate("Flags", "Delete flag type"))
    from . import levels
    difference = FlagDifference(removals=[flagType])
    for level in levels.allLevels:
        if level == levels.real:
            elementIds = db.query("SELECT element_id FROM {p}flags WHERE flag_id=?", flagType.id)\
                                  .getSingleColumn()
            elements = level.collectMany(elementIds)
        else: elements = [el for el in level.elements.values() if flagType in el.flags]
        if len(elements) > 0:
            level.changeFlags({element: difference for element in elements})
    stack.push('', stack.Call(_deleteFlagType, flagType), stack.Call(_addFlagType, flagType))
    stack.endMacro()
    
    
def _deleteFlagType(flagType):
    """Like deleteFlagType but not undoable."""
    if not exists(flagType.name):
        raise ValueError("Cannot remove flagtype '{}' because it does not exist.".format(flagType))
    
    logging.info(__name__, "Deleting flag '{}'.".format(flagType))
    db.query("DELETE FROM {p}flag_names WHERE id = ?", flagType.id)
    del _flagsById[flagType.id]
    del _flagsByName[flagType.name]
    application.dispatcher.emit(FlagTypeChangedEvent(DELETED, flagType))


def changeFlagType(flagType, **data):
    """Change a flagtype. The attributes that should be changed must be specified by keyword arguments.
    Supported are 'name' and 'iconPath':
        changeFlagType(flagType, name='Great', iconPath=None)
    """
    oldData = {'name': flagType.name, 'iconPath': flagType.iconPath}
    stack.push(translate("Flags", "Change flag type"),
               stack.Call(_changeFlagType, flagType, **data),
               stack.Call(_changeFlagType, flagType, **oldData))
    
    
def _changeFlagType(flagType, **data):
    """Like changeFlagType but not undoable."""
    # Below we will build a query like UPDATE flag_names SET ... using the list of assignments (e.g. (name=?).
    # The parameters will be sent with the query to replace the questionmarks.
    assignments = []
    params = []
    
    if 'name' in data:
        name = data['name']
        if name != flagType.name:
            if exists(name):
                raise ValueError("There is already a flag named '{}'.".format(name))
            logging.info(__name__, "Changing flag name '{}' to '{}'.".format(flagType.name, name))
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
        db.query("UPDATE {p}flag_names SET "+','.join(assignments)+" WHERE id = ?", *params)
        application.dispatcher.emit(FlagTypeChangedEvent(CHANGED, flagType))


class FlagTypeChangedEvent(ChangeEvent):
    """FlagTypeChangedEvent are used when a flagtype is added, changed or deleted."""
    def __init__(self, action, flagType):
        assert action in constants.CHANGE_TYPES
        self.action = action
        self.flagType = flagType


class FlagDifference:
    """Stores changes to flag lists and provides methods to apply them. When this difference is applied to
    an element the flags in *removals* will be removed from the elements flags and the flags in *additions*
    will be added.
    """
    def __init__(self, additions=None, removals=None):
        self._additions = additions
        self._removals = removals
        
    def apply(self, element):
        """Change the flags of *element* according to this difference object."""
        if self._removals is not None:
            for flag in self._removals:
                element.flags.remove(flag)
        if self._additions is not None:
            element.flags.extend(self._additions)

    def revert(self, element):
        """Undo the changes of this difference object to the flags of *element*."""
        if self._additions is not None:
            for flag in self._additions:
                element.flags.remove(flag)
        if self._removals is not None:
            element.flags.extend(self._removals)
            
    def getAdditions(self):
        """Return the list of flags which are added by this difference."""
        return self._additions if self._additions is not None else []
        
    def getRemovals(self):
        """Return the list of flags which are removed by this difference."""
        return self._removals if self._removals is not None else []
        
    def inverse(self):
        """Return the inverse difference."""
        return utils.InverseDifference(self)
            

class FlagListDifference(FlagDifference):
    """Subclass of FlagDifference that simply takes two lists of flags (old and new) and figures out
    additions/removals by itself."""
    def __init__(self, oldFlags, newFlags):
        self.oldFlags = oldFlags
        self.newFlags = newFlags
                
    def apply(self, element):
        element.flags = self.newFlags[:]
        
    def revert(self, element):
        element.flags = self.oldFlags[:]
        
    def getAdditions(self):
        return [flag for flag in self.newFlags if not flag in self.oldFlags]
    
    def getRemovals(self):
        return [flag for flag in self.oldFlags if not flag in self.newFlags]
 