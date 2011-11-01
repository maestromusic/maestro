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

from . import database as db, modify, logging, constants
from PyQt4 import QtGui


logger = logging.getLogger(__name__)

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
    
    Usually you shold get tag instances via the :func:`get-method<omg.tags.get>`. The exception is for
    tags that are not (yet) in the database (use :func:`exists` to check this). For these tags
    :func:`get` will fail and you have to create your own instances. If you use the common instance, it
    will get automatically updated on TagTypeChangeEvents.
    """
    def __init__(self,id,name,iconPath):
        self.id = id
        self.name = name
        self.setIconPath(iconPath)
    
    def setIconPath(self,iconPath):
        """Set the flag's iconPath and load the icon."""
        self.iconPath = iconPath
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


def addFlagType(name,iconPath):
    """Add a new flag with the given name to the database, emit a FlagTypeChangedEvent and return
    the new flag."""
    if exists(name):
        raise ValueError("There is already a flag named '{}'.".format(name))
    
    logger.info("Adding new flag '{}'.".format(name))
    id = db.query("INSERT INTO {}flag_names (name,icon) VALUES (?,?)"
                    .format(db.prefix),name,iconPath).insertId()
    newFlag = Flag(id,name,iconPath)
    _flagsById[id] = newFlag
    _flagsByName[name] = newFlag
    
    modify.dispatcher.changes.emit(modify.events.FlagTypeChangedEvent(modify.ADDED,newFlag))
    return newFlag


def removeFlagType(flagType):
    """Remove the given *flagType* from the database and emit a FlagTypeChangedEvent."""
    if not exists(flagType.name):
        raise ValueError("Cannot remove flagtype '{}' because it does not exist.".format(flagType))
    
    logger.info("Removing flag '{}'.".format(flagType))
    db.query("DELETE FROM {}flag_names WHERE id = ?".format(db.prefix),flagType.id)
    del _flagsById[flagType.id]
    del _flagsByName[flagType.name]
    modify.dispatcher.changes.emit(modify.events.FlagTypeChangedEvent(modify.DELETED,flagType))


def changeFlagType(flagType,name=None,iconPath=''):
    """Change the name and/or iconPath of *flagType* in the database and emit an event. If name or iconPath
    is not given, it will not be changed. Set iconPath to None to remove the icon."""    
    assignments = []
    data = []
    
    if name is not None and name != flagType.name:
        if exists(name):
            raise ValueError("There is already a flag named '{}'.".format(name))
        logger.info("Changing flag name '{}' to '{}'.".format(flagType.name,name))
        assignments.append('name = ?')
        data.append(name)
        flagType.name = name
        
    if iconPath != '' and iconPath != flagType.iconPath:
        assignments.append('icon = ?')
        data.append(iconPath)
        flagType.setIconPath(iconPath)
    
    if len(assignments) > 0:
        data.append(flagType.id) # for the where clause
        db.query("UPDATE {}flag_names SET {} WHERE id = ?".format(db.prefix,','.join(assignments)),*data)
        modify.dispatcher.changes.emit(modify.events.FlagTypeChangedEvent(modify.CHANGED,flagType))
