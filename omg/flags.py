#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#

from . import database as db, modify, logging
from PyQt4 import QtGui


logger = logging.getLogger(__name__)


class Flag:
    """A flagtype with an id, a name an optionally an icon. At first glance flags are like tags, but in fact
    they are much easier, because they have no values, valuetypes, translations and because they are not
    stored in files.
    
    Note: Contrary to tags you should use the constructor of Flags. So while there will usually be only one
    instance for each tag, there may be many for each flagtype.
    """
    def __init__(self,id,name,iconPath):
        self.id = id
        self.name = name
        self.iconPath = iconPath
        self.icon = QtGui.QIcon(iconPath)
        
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
        name = db.query("SELECT name FROM {}flag_names WHERE id = ?"
                        .format(db.prefix),identifier).getSingle()
        return Flag(identifier,name)
    elif isinstance(identifier,str):
        id = db.query("SELECT id FROM {}flag_names WHERE name = ?"
                        .format(db.prefix),identifier).getSingle()
        return Flag(id,identifier)
    elif isinstance(identifier,FlagType):
        return identifier
    else: raise ValueError("identifier must be either int or string or FlagType.")


def exists(name):
    """Return whether a flagtype with the given name exists."""
    return bool(db.query("SELECT COUNT(*) FROM {}flag_names WHERE name = ?".format(db.prefix),name)
                    .getSingle())


def isValidFlagname(name):
    """Return whether *name* is a valid name for a flagtype."""
    return len(name) > 0 and not name.isspace()


def allFlags():
    """Return a list containing all flags in the database."""
    return [Flag(*row) for row in db.query("SELECT id,name FROM {}flag_names ORDER BY name"
                                                .format(db.prefix))]


def addFlagType(name,iconPath):
    """Add a new flag with the given name to the database and return it."""
    if exists(name):
        raise ValueError("There is already a flag named '{}'.".format(name))
    
    logger.info("Adding new flag '{}'.".format(name))
    id = db.query("INSERT INTO {}flag_names (name,icon) VALUES (?,?)"
                    .format(db.prefix),name,iconPath).insertId()
    newFlag = Flag(id,name,iconPath)
    modify.dispatcher.changes.emit(modify.events.FlagTypeChangedEvent(modify.ADDED,newFlag))
    return newFlag


def removeFlagType(flagType):
    """Remove the given *flagType* from the database."""
    if not exists(flagType.name):
        raise ValueError("Cannot remove flagtype '{}' because it does not exist.".format(flagType))
    
    logger.info("Removing flag '{}'.".format(flagType))
    db.query("DELETE FROM {}flag_names WHERE id = ?".format(db.prefix),flagType.id)
    modify.dispatcher.changes.emit(modify.events.FlagTypeChangedEvent(modify.DELETED,flagType))


def changeFlagType(flagType,name,iconPath):
    """Change the name of *flagType* in the database and return a new FlagType-instance with the new name."""    
    assignments = []
    data = []
    
    if name != flagType.name:
        if exists(name):
            raise ValueError("There is already a flag named '{}'.".format(name))
        logger.info("Changing flag name '{}' to '{}'.".format(flagType.name,name))
        assignments.append('name = ?')
        data.append(name)
        
    if iconPath != flagType.iconPath:
        assignments.append('icon = ?')
        data.append(iconPath)
    
    if len(assignments) > 0:
        data.append(flagType.id) # for the where clause
        db.query("UPDATE {}flag_names SET {} WHERE id = ?".format(db.prefix,','.join(assignments)),*data)
        newFlagType = Flag(flagType.id,name,iconPath)
        modify.dispatcher.changes.emit(modify.events.FlagTypeChangedEvent(modify.CHANGED,newFlagType))
        return newFlagType
    else: return flagType
