#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#

from . import database as db, modify, logging

logger = logging.getLogger(__name__)


class FlagType:
    """A flagtype with an id and a name. At first glance flags are like tags, but in fact they are much
    easier, because they have no values, valuetypes, translations and because they are not stored in files.
    
    Note: Contrary to tags you should use the constructor of Flags. So while there will usually be only one
    instance for each tag, there may be many for each flagtype.
    """
    def __init__(self,id,name):
        self.id = id
        self.name = name
        
    def __str__(self):
        return self.name
    
    def __eq__(self,other):
        return isinstance(other,FlagType) and self.id == other.id
    
    def __ne__(self,other):
        return not isinstance(other,FlagType) or self.id != other.id
    
    def __hash__(self):
        return self.id
        

def get(identifier):
    """Return a flagtype. *identifier* may be an int (the flag's id), a string (its name) or a flagtype (in
    this case it is simply returned)."""
    if isinstance(identifier,int):
        name = db.query("SELECT name FROM {}flag_names WHERE id = ?"
                        .format(db.prefix),identifier).getSingle()
        return FlagType(identifier,name)
    elif isinstance(identifier,str):
        id = db.query("SELECT id FROM {}flag_names WHERE name = ?"
                        .format(db.prefix),identifier).getSingle()
        return FlagType(id,identifier)
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


def all():
    """Return a list containing all flagnames from the database."""
    return db.query("SELECT name FROM {}flag_names".format(db.prefix)).getSingleColumn()


def addFlagType(name):
    """Add a new flag with the given name to the database and return it."""
    if exists(name):
        raise ValueError("There is already a flag named '{}'.".format(name))
    
    logger.info("Adding new flag '{}'.".format(name))
    id = db.query("INSERT INTO {}flag_names (name) VALUES (?)".format(db.prefix),name).insertId()
    newFlag = FlagType(id,name)
    modify.dispatcher.changes.emit(modify.events.FlagTypeChangedEvent(modify.ADDED,newFlag))
    return newFlag


def removeFlagType(flagType):
    """Remove the given *flagType* from the database."""
    if not exists(flagType.name):
        raise ValueError("Cannot remove flagtype '{}' because it does not exist.".format(flagType))
    
    logger.info("Removing flag '{}'.".format(flagType))
    db.query("DELETE FROM {}flag_names WHERE id = ?".format(db.prefix),flagType.id)
    modify.dispatcher.changes.emit(modify.events.FlagTypeChangedEvent(modify.DELETED,flagType))


def changeFlagType(flagType,name):
    """Change the name of *flagType* in the database and return a new FlagType-instance with the new name."""
    if name == flagType.name:
        return flagType
    
    if exists(name):
        raise ValueError("There is already a flag named '{}'.".format(name))
    
    logger.info("Changing flag '{}' to '{}'.".format(flagType.name,name))
    db.query("UPDATE {}flag_names SET name = ? WHERE id = ?".format(db.prefix),name,flagType.id)
    newFlagType = FlagType(flagType.id,name)
    modify.dispatcher.changes.emit(modify.events.FlagTypeChangedEvent(modify.CHANGED,newFlagType))
    return newFlagType
        
