# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2013 Martin Altmayer, Michael Helmling
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

from omg import database as db
from omg import config
from omg.core import tags
translate = QtCore.QCoreApplication.translate

def defaultStorage():
    return {"SECTION:musicbrainz": {'tagmap': {},
                                }
            }

def defaultConfig():
    return {"musicbrainz": {
            "queryCacheDays": (int, 7, "Number of days after which cached web service calls expire.")
        }}

tagMap = {}

def enable():
    #profileType = profiles.ProfileType('musicbrainz',
    #                                   translate('musicbrainz', 'MusicBrainz profile'),
    #                                   MusicBrainzGuesser)
    #albumguesser.profileCategory.addType(profileType) needs to be rewritten
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
    for mbtag, omgname in confMap.items():
        if omgname:
            omgtag = tags.get(omgname)
            if omgtag.isInDb():
                tagMap[mbtag] = omgtag
        else:
            tagMap[mbtag] = None
    
def disable():
    global tagMap
    tagMap = {}
    #albumguesser.profileCategory.removeType('musicbrainz')

def aliasFromDB(entity, mbid):
    try:
        return db.query("SELECT alias, sortname FROM {}musicbrainzaliases "
                        "WHERE entity=? AND mbid=?".format(db.prefix),
                        entity, mbid).getSingleRow()
    except db.sql.EmptyResultException:
        return None
    
def updateDBAliases(entities):
    for ent in entities:
        db.query("DELETE FROM {}musicbrainzaliases WHERE entity=? AND mbid=?"
                 .format(db.prefix), ent.type, ent.mbid)
        if not ent.isDefault():
            db.query("INSERT INTO {}musicbrainzaliases (entity, mbid, alias, sortname) "
                     "VALUES (?,?,?,?)".format(db.prefix),
                     ent.type, ent.mbid, ent.name, ent.sortName)
            
# class MusicBrainzGuesser(profiles.Profile):
#     
#     def __init__(self, name, type, state):
#         super().__init__(name, type, state)
#     
#     def guessAlbums(self, level, files):
#         self.toplevels = []
#         for dirname, elements in files.items():
#             hashes = {elem: db.hash(elem.id) if elem.isInDb() else filesystem.getNewfileHash(elem.url)
#                       for elem in elements}
#             if all(hash.startswith("mbid") for hash in hashes.values()):
#                 print('good')
#             else:
#                 print('bad')
#                 self.toplevels.extend(elements)
#                 continue
#             releases = {}
#             for elem, hash in hashes.items():
#                 response = req.urlopen("http://musicbrainz.org/ws/2/recording/{}?inc=releases".format(hash[5:]))
#                 data = response.readall()
#                 root = ET.fromstring(data)
#                 release = next(root.iter("{http://musicbrainz.org/ns/mmd-2.0#}release")).attrib["id"]
#                 if release not in releases:
#                     releases[release] = []
#                 releases[release].append(elem)
#             for release, elements in releases.items():
#                 print("release {}".format(release))
#                 for elem in elements:
#                     print("  {}".format(elem.url))
#             self.toplevels.extend(elements)