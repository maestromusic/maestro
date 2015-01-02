# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2013-2014 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtCore, QtGui
translate = QtCore.QCoreApplication.translate

from ... import database as db
from ... import config
from ...core import tags, domains


def defaultStorage():
    return {"musicbrainz": {'tagmap': ({},),
                                }
            }


def defaultConfig():
    return {"musicbrainz": {
            "queryCacheDays": (int, 7, "Number of days after which cached web service calls expire."),
            'domain':         (str, domains.domains[0].name, 'domain for new containers')
        }}

tagMap = {}


def enable():
    db.query("CREATE TABLE IF NOT EXISTS {}musicbrainzqueries ("
             "url VARCHAR(256), "
             "verified TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
             "xml TEXT)".format(db.prefix))
    db.query("DELETE FROM {}musicbrainzqueries WHERE "
             "datetime('now', '-{} days') >= verified"
             .format(db.prefix, config.options.musicbrainz.queryCacheDays))
    db.query("CREATE TABLE IF NOT EXISTS {}musicbrainzaliases ("
             "entity VARCHAR(16), "
             "mbid VARCHAR(128), "
             "alias VARCHAR(256), "
             "sortname VARCHAR(256))".format(db.prefix))

    global tagMap
    confMap = config.storage.musicbrainz.tagmap
    for mbtag, maestroName in confMap.items():
        if maestroName:
            maestroTag = tags.get(maestroName)
            if maestroTag.isInDb():
                print(mbtag, maestroTag)
                tagMap[mbtag] = maestroTag
        else:
            tagMap[mbtag] = None
    

def disable():
    global tagMap
    tagMap = {}


def aliasFromDB(entity, mbid):
    try:
        return db.query("SELECT alias, sortname FROM {}musicbrainzaliases "
                        "WHERE entity=? AND mbid=?".format(db.prefix),
                        entity, mbid).getSingleRow()
    except db.EmptyResultException:
        return None
    

def updateDBAliases(entities):
    for ent in entities:
        db.query("DELETE FROM {}musicbrainzaliases WHERE entity=? AND mbid=?"
                 .format(db.prefix), ent.type, ent.mbid)
        if not ent.isDefault():
            db.query("INSERT INTO {}musicbrainzaliases (entity, mbid, alias, sortname) "
                     "VALUES (?,?,?,?)".format(db.prefix),
                     ent.type, ent.mbid, ent.name, ent.sortName)
