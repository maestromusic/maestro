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

import urllib.request
import urllib.error

from lxml import etree

from ... import config, database as db, logging
from ...core import elements, tags
from ...core.elements import TYPE_ALBUM
from ...utils import FlexiDate
from ...filebackends import BackendURL

from . import plugin as mbplugin

logger = logging.getLogger("musicbrainz.xmlapi")

wsURL = "http://musicbrainz.org/ws/2" # the base URL for MusicBrainz' web service

queryCallback = None


class UnknownDiscException(Exception):
    """Raised when a disc ID is not known in the musicbrainz database."""
    pass


def query(resource, mbid, includes=[]):
    """Queries MusicBrainz' web service for *resource* with *mbid* and the given list of includes.
    
    Returns an LXML ElementTree root node. All namespaces are removed from the result.
    """
    url = "{}/{}/{}".format(wsURL, resource, mbid)
    if queryCallback:
        queryCallback(url)
    if len(includes) > 0:
        url += "?inc={}".format("+".join(includes))
    logger.debug('querying {}'.format(url))
    ans = db.query("SELECT xml FROM {}musicbrainzqueries WHERE url=?".format(db.prefix), url)
    try:
        data = ans.getSingle()
    except db.EmptyResultException:
        try:
            with urllib.request.urlopen(url) as response:
                data = response.readall()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise e
            else:
                raise ConnectionError(e.msg)
        db.query("INSERT INTO {}musicbrainzqueries (url, xml) VALUES (?,?)"
                 .format(db.prefix), url, data)
    root = etree.fromstring(data)
    # remove namespace tags
    for node in root.iter(): 
        if node.tag.startswith('{'):
            node.tag = node.tag.rsplit('}', 1)[-1]
    return root


class MBTagStorage(dict):
    """A basic storage for MusicBrainz tags.
    
    In contrast to tags.Storage it allows AliasEntity values."""
    
    def __setitem__(self, key, value):        
        if isinstance(value, str) or isinstance(value, AliasEntity):
            value = [value]
        super().__setitem__(key, value)
        
    def add(self, key, value):
        if key in self:
            if value not in self[key]:
                self[key].append(value)
        else:
            self[key] = [value]
            
    def asMaestroTags(self, mapping=None):
        """Convert the MBTagStorage to an maestro.tags.Storage object.
        
        *mapping* may be a dict mapping strings to Maestro tag types.
        """
        ret = tags.Storage()
        for key, values in self.items():
            if mapping and key in mapping:
                if mapping[key] is None:
                    continue
                else:
                    tag = mapping[key]
            else:
                tag = tags.get(key)
            ret[tag] = [ str(v) for v in values ] # converts AliasEntities to strings
        return ret


class Alias:
    """An alias for a MusicBrainz entry.
    
    Attributes:
        name (str): the actual alias
        sortName (str): value used for sorting; may be None
        primary (bool): either True or False; at most one primary alias per locale
        locale: describes the locale for which the alias is valid
    """
    
    def __init__(self, name, sortName, primary=False, locale=None):
        self.name = name
        if sortName is None:
            sortName = name
        self.sortName = sortName
        self.primary = primary
        self.locale = locale
    
    def __gt__(self, other):
        """Compares lexicographically but primaries and aliases with locales are at the front."""
        if self.primary > other.primary:
            return False
        if self.primary < other.primary:
            return True
        if bool(self.locale) > bool(other.locale):
            return False
        if bool(self.locale) < bool(other.locale):
            return True
        if self.locale and self.locale > other.locale:
            return True
        return self.name > other.name

        
class AliasEntity:
    """A musicbrainz entity that may have aliases, i.e., artists and work titles.
    """
    _entities = {}
    
    @staticmethod
    def get(node):
        mbid = node.get("id")
        if mbid in AliasEntity._entities:
            return AliasEntity._entities[mbid]
        type = node.tag
        name = node.findtext("name") if node.tag == "artist" else node.findtext("title")
        sortName = node.findtext("sort-name")
        ent = AliasEntity(type, mbid, name, sortName)
        # if this entity is stored in the DB table, set the previously used name and sortName
        # as default
        ans = mbplugin.aliasFromDB(type, mbid)
        if ans:
            ent.name, ent.sortName = ans
        AliasEntity._entities[mbid] = ent
        return ent
        
    
    def __init__(self, type, mbid, name, sortName):
        self.type = type
        self.mbid = mbid
        self.name = name
        self.aliases = [Alias(name, sortName)]
        self.asTag = set()
        self.selectAlias(0)
        self.loaded = False
    
    def selectAlias(self, index):
        self.name = self.aliases[index].name
        self.sortName = self.aliases[index].sortName

    def loadAliases(self):
        """Queries the MusicBrainz web service for aliases."""
        if self.loaded:
            return
        result = query(self.type, self.mbid, ("aliases",))
        newaliases = []
        for alias in result.iter("alias"):
            alias = Alias(alias.text, alias.get("sort-name"),
                          bool(alias.get("primary")), alias.get("locale"))
            newaliases.append(alias)
        self.aliases.extend(sorted(newaliases))
        self.loaded = True
        return self.aliases

    def isDefault(self):
        return self.name == self.aliases[0].name and self.sortName == self.aliases[0].sortName
    
    def __str__(self):
        return self.name

    def __repr__(self):
        return "AliasEntity({},{})".format(self.type, self.name)
    
    def __eq__(self, other):
        if not isinstance(other, AliasEntity):
            return False
        return self.mbid == other.mbid and self.type == other.type
    
    def __hash__(self):
        return int(self.mbid.replace("-", ""), 16)
    
    def url(self):
        return "http://www.musicbrainz.org/{}/{}".format(self.type, self.mbid)


def findReleasesForDiscid(discid):
    """Finds releases containing specified disc using MusicBrainz.
    
    Returns a list of Release objects, containing Medium objects but no
    recordings.
    """
    try:
        root = query("discid", discid, ("artists", "release-groups"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise UnknownDiscException()
        else:
            raise e
    releases = []
    from .elements import Release, Medium
    for release in root.iter("release"):
        mbit = Release(release.get("id"))
        title = release.findtext('title')
        for medium in release.iterfind('medium-list/medium'):
            pos = int(medium.findtext('position'))
            disctitle = medium.findtext('title')
            discids = [disc.get("id") for disc in medium.iterfind('disc-list/disc')]
            Medium(pos, mbit, discids, disctitle)
        mbit.tags.add('title', title)
        
        artists = release.iterfind('artist-credit/name-credit/artist')
        if artists:
            for art in artists:
                ent = AliasEntity.get(art)
                ent.asTag.add("artist")
                mbit.tags.add("artist", ent)
        if release.find('date') is not None:
            mbit.tags.add("date", FlexiDate(*release.findtext('date').split('-')))
        if release.find('country') is not None:
            mbit.tags.add("country", release.findtext('country'))
        if release.find('barcode') is not None:
            mbit.tags.add("barcode", release.findtext('barcode'))
        relGroup = release.find('release-group')
        if relGroup is not None and relGroup.get("type") == "Compilation":
            mbit.containerType = elements.TYPE_COLLECTION
            for medium in mbit.children.values():
                medium.containerType = elements.TYPE_ALBUM
                medium.tags.add('album', medium.tags['title'][0])
        else:
            mbit.tags.add('album', title)
        releases.append(mbit)
    if len(releases) == 0:
        raise UnknownDiscException("No release for disc ID {}".format(discid))
    return releases

    
def fillReleaseForDisc(MBrelease, discid):
    """Given a stub Release object *MBrelease* (as created by findReleasesForDiscid) and a disc id,
    creates recordings, works etc. for the given disc.
    """
    release = query("release", MBrelease.mbid, ("recordings",)).find("release")
    
    pos, MBmedium = MBrelease.mediumForDiscid(discid)
    MBmedium.currentDiscid = discid
    from .elements import Recording, Medium
    # find the medium in the xml tree
    for medium in release.iterfind('medium-list/medium'):
        if int(medium.findtext('position')) == pos:
            break
    for track in medium.iterfind('track-list/track'):
        recording = track.find('recording')
        tracknr = int(track.findtext('number'))
        MBrec = Recording(recording.get("id"), int(track.findtext("position")), MBmedium, tracknr)
        MBrec.tags.add("title", recording.findtext("title"))
        MBrec.backendUrl = BackendURL.fromString("audiocd://{0}.{1}/{2}/{0}/{1}.flac"
                                                 .format(discid, tracknr, config.options.audiocd.rippath))
    for _, MBrec in sorted(MBmedium.children.items()):
        MBrec.lookupInfo()
    MBmedium.insertWorks()
    if len(MBrelease.children) == 1:
        logger.debug("single child release -> removing release container")
        del MBrelease.children[pos]
        for p, child in MBmedium.children.items():
            MBrelease.insertChild(p, child)
        MBrelease.passTags(excludes=['title'])
    for p in list(MBrelease.children.keys()):
        if isinstance(MBrelease.children[p], Medium) and MBrelease.children[p] != MBmedium:
            logger.debug("ignoring other child {}".format(MBrelease.children[p]))
            MBrelease.children[p].ignore = True
            
