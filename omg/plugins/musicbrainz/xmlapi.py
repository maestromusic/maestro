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

from lxml import etree
import urllib.request as req

from omg import database as db
from omg.core import elements, tags
from omg.utils import FlexiDate
from omg.filebackends import BackendURL
from omg import logging

logger = logging.getLogger("musicbrainz.xmlapi")

wsURL = "http://musicbrainz.org/ws/2"


def query(resource, mbid, includes=[]):
    """Queries MusicBrainz' web service for *resource* with *mbid* and the given list of includes.
    
    Returns an LXML ElementTree root node. All namespaces are removed from the result.
    """
    
    url = "{}/{}/{}".format(wsURL, resource, mbid)
    if len(includes) > 0:
        url += "?inc={}".format("+".join(includes))
    ans = db.query("SELECT xml FROM {}musicbrainzqueries WHERE url=?".format(db.prefix), url)
    if len(ans):
        data = ans.getSingle()
    else:
        with req.urlopen(url) as response:
            data = response.readall()
        db.query("INSERT INTO {}musicbrainzqueries (url, xml) VALUES (?,?)"
                 .format(db.prefix), url, data)
    root = etree.fromstring(data)
    # remove namespace tags
    for node in root.iter(): 
        if node.tag.startswith('{'):
            node.tag = node.tag.rsplit('}', 1)[-1]
    return root


class MBTagStorage(dict):
    """A basic tag storage. In contrast to tags.Storage it allows AliasEntity values."""
    
    def __setitem__(self, key, value):        
        if isinstance(value, str) or isinstance(value, AliasEntity):
            value = [value]
        super().__setitem__(key, value)
        
    def add(self, key, value):
        if key in self:
            self[key].append(value)
        else:
            self[key] = [value]
            
    def asOMGTags(self, mapping=None):
        ret = tags.Storage()
        for key, values in self.items():
            if mapping and key in mapping:
                if mapping[key] is None:
                    continue
                else:
                    tag = mapping[key]
            else:
                tag = tags.get(key)
            ret[tag] = [ str(v) if isinstance(v, AliasEntity) else v for v in values ]
        return ret


class Alias:
    """An alias for a MusicBrainz entry.
    
    Has the following attributes:
    - name: the actual alias
    - sortName: value used for sorting; may be None
    - primary: either True or False; at most one primary alias per locale
    - locale: describes the locale for which the alias is valid
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

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return self.mbid == other.mbid and self.type == other.type
    
    def __hash__(self):
        return int(self.mbid.replace("-", ""), 16)
    
    def url(self):
        return "http://www.musicbrainz.org/{}/{}".format(self.type, self.mbid)


class MBTreeItem:
    
    def __init__(self, mbid):
        self.mbid = mbid
        self.tags = MBTagStorage()
        self.children = {}
        self.parent = None
        self.pos = None
        
    def insertChild(self, pos, child):
        if pos is None:
            if len(self.children) == 0:
                pos = 1
            else:
                pos = max(self.children.keys()) + 1
        self.children[pos] = child
        child.pos = pos
        child.parent = self
    
    def __str__(self):
        return "{}(mbid={})".format(self.__class__.__name__, self.mbid)
    
    def __eq__(self, other):
        return self.mbid == other.mbid
    
    def walk(self):
        yield self
        for child in self.children.values():
            yield from child.walk()
     
    def makeElements(self, level):
        if not isinstance(self, Recording):
            contentList = elements.ContentList()
            for pos, child in self.children.items():
                element = child.makeElements(level)            
                contentList.insert(pos, element.id)
            element = level.createContainer(tags=self.tags.asOMGTags(), contents=contentList)
        else:
            element = level.collect(self.backendUrl)
            diff = tags.TagStorageDifference(None, self.tags.asOMGTags())
            level.changeTags({element: diff})
        element.mbItem = self
        self.element = element
        return element
        
    def collectAliasEntities(self):
        entities = set()
        import itertools
        for item in self.walk():
            for val in itertools.chain.from_iterable(item.tags.values()):
                if isinstance(val, AliasEntity):
                    entities.add(val)
        return entities

    def collectExternalTags(self):
        etags = set()
        for item in self.walk():
            for tag in item.element.tags:
                if not tag.isInDb():
                    etags.add(tag)
        return etags
    
class Release(MBTreeItem):
    """A release is the top-level container structure in MusicBrainz that we care about.
    """
    
    def mediumForDiscid(self, discid):
        """Return the position of the medium in this release with given *discid*, if such exists.
        """
        for pos, child in self.children.items():
            if discid in child.discids:
                return pos


class Medium(MBTreeItem):
    """A medium inside a release. Usually has one or more discids associated to it."""
    
    def __init__(self, pos, release, discids, title=None):
        """Create the medium with associated *discids* as position *pos* in *release*.
        
        It will be inserted into *release* at the given position. *discids* is a list of disc
        IDs associated to that medium.
        If the medium has a title, that may be given as will. It will be inserted into the
        medium's tags as "title".
        """
        super().__init__(mbid=None)
        release.insertChild(pos, self)
        if not title:
            title = "Disc {}".format(pos)
        self.tags.add("title", title)
        self.discids = set(discids)
    
    def insertWorks(self):
        """Inserts superworks as intermediate level between the medium and its recording.
        
        This method assumes that all childs of *self* are Recording instances.
        """
        newChildren = []
        posOffset = 0
        for pos, child in sorted(self.children.items()):
            if child.parentWork:
                if len(newChildren) and newChildren[-1][1] == child.parentWork:
                    newChildren[-1][1].insertChild(None, child)
                    
                    posOffset -= 1
                else:
                    newChildren.append((child.pos + posOffset, child.parentWork))
                    child.parentWork.insertChild(None, child)
                    child.parentWork.lookupInfo(False)
                child.parentWork = None
            else:
                newChildren.append((child.pos + posOffset, child))
        self.children.clear()
        for pos, child in newChildren:
            self.insertChild(pos, child)
    
    def __eq__(self, other):
        return self is other


class Recording(MBTreeItem):
    """A recording is a unique piece of recorded audio.
    
    Every track on a CD is associated to exactly one recording. Since we don't care about tracks,
    we immediately insert Recordings as children of media.
    """
    
    def __init__(self, recordingid, pos, parent, tracknumber):
        """Create recording with the given id and insert it at *pos* under *parent*.
        
        Since the MusicBrainz position could theoretically be different from the tracknumber, the
        latter is needed as well.
        """
        super().__init__(recordingid)
        parent.insertChild(pos, self)
        self.tags.add("musicbrainz_recordingid", self.mbid)
        self.tracknumber = tracknumber
        self.parentWork = self.workid = None
        
    def lookupInfo(self):
        """Queries MusicBrainz for tag information and potential related works."""
        recording = query("recording",
                          self.mbid,
                          ("artist-rels", "work-rels", "artists")
                         ).find("recording")
        for artistcredit in recording.iterfind("artist-credit"):
            for child in artistcredit:
                if child.tag == "name-credit":
                    ent = AliasEntity.get(child.find("artist"))
                    ent.asTag.add("artist")
                    self.tags.add("artist", ent)
                else:
                    logger.warning("unknown artist-credit {} in recording {}"
                                   .format(child.tag, self.mbid))
        
        for relation in recording.iterfind('relation-list[@target-type="artist"]/relation'):
            artist = AliasEntity.get(relation.find("artist"))
            reltype = relation.get("type")
            simpleTags = {"conductor" : "conductor",
                          "performing orchestra" : "performer:orchestra",
                          "arranger" : "arranger",
                          "chorus master" : "chorusmaster",
                          "performer" : "performer",
                          "engineer" : "engineer",
                          "producer" : "producer"}
            
            if reltype == "instrument":
                instrument = relation.findtext("attribute-list/attribute")
                tag = "performer:"+instrument
            elif reltype in simpleTags:
                tag = simpleTags[reltype]
            elif reltype == "vocal":
                voice = relation.findtext("attribute-list/attribute")
                for vtype in "soprano", "mezzo-soprano", "tenor", "baritone":
                    if voice.startswith(vtype):
                        tag = "performer:" + vtype
                        continue
                if voice == "choir vocals":
                    tag = "performer:choir"
                else:
                    logger.warning("unknown voice: {} in {}".format(voice, self.mbid))
            else:
                logger.warning("unknown artist relation '{}' in recording '{}'"
                               .format(relation.get("type"), self.mbid))
                continue
            self.tags.add(tag, artist)
            artist.asTag.add(tag)
        for i, relation in enumerate(recording.iterfind('relation-list[@target-type="work"]/relation')):
            if i > 0:
                logger.warning("more than one work relation in recording {}".format(self.mbid))
                break
            if relation.get("type") == "performance":
                workid = relation.findtext("target")
                work = Work(workid)
                work.lookupInfo()
                self.mergeWork(work)
            else:
                logger.warning("unknown work relation '{}' in recording '{}'"
                               .format(relation.get("type"), self.mbid))
        
    def mergeWork(self, work):
        logger.debug("merging work {} into recording {}".format(work.mbid, self.mbid))
        self.workid = work.mbid
        for tag, values in work.tags.items():
            if tag in self.tags:
                if tag == "title":
                    self.tags[tag] = values[:]
                else:
                    self.tags[tag].extend(values)
            else:
                self.tags[tag] = values
        self.parentWork = work.parentWork
        

class Work(MBTreeItem):
    
    def __init__(self, workid):
        super().__init__(workid)
        self.parentWork = None
        self.tags.add("musicbrainz_workid", self.mbid)

    def lookupInfo(self, works=True):
        incs =  ["artist-rels"] + (["work-rels"] if works else [])
        work = query("work", self.mbid, incs).find("work")
        ent = AliasEntity.get(work)
        ent.asTag.add("title")
        self.tags.add("title", ent)
        for relation in work.iterfind('relation-list[@target-type="artist"]/relation'):
            easyRelations = { "composer" : "composer",
                              "lyricist" : "lyricist",
                              "orchestrator" : "orchestrator"
                            }
            reltype = relation.get("type")
            artist = AliasEntity.get(relation.find('artist'))
            if reltype in easyRelations:
                artist.asTag.add(easyRelations[reltype])
                self.tags.add(easyRelations[reltype], artist)
            else:
                logger.warning("unknown work-artist relation {} in work {}"
                               .format(reltype, self.mbid))
        
        for relation in work.iterfind('relation-list[@target-type="work"]/relation'):
            if relation.get("type") == "parts":
                assert relation.findtext("direction") == "backward"
                assert self.parentWork is None
                parentWorkId = relation.find('work').get('id')
                self.parentWork = Work(parentWorkId)
                self.parentWork.tags["title"] = [relation.findtext('work/title')]
            else:
                logger.debug("unknown work-work relation {} in {}".format(relation.get("type"), self.mbid))
                


def findReleasesForDiscid(discid):
    """Finds releases containing specified disc using MusicBrainz.
    
    Returns a list of Release objects, containing Medium objects but no
    recordings.
    """
    root = query("discid", discid, ("artists",))
    releases = []
    for release in root.iter("release"):
        mbit = Release(release.get("id"))
        title = release.findtext('title')
        for medium in release.iterfind('medium-list/medium'):
            pos = int(medium.findtext('position'))
            disctitle = medium.findtext('title')
            discids = [disc.get("id") for disc in medium.iterfind('disc-list/disc')]
            Medium(pos, mbit, discids, disctitle if disctitle else None)
        mbit.tags.add('title', title)
        mbit.tags.add('musicbrainz_releasid', mbit.mbid)
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
        releases.append(mbit)
    return releases

    
def makeReleaseContainer(MBrelease, discid, level):
    release = query("release", MBrelease.mbid, ("recordings",)).find("release")
    
    # find the correct medium
    pos = MBrelease.mediumForDiscid(discid)
    MBmedium = MBrelease.children[pos]
    
    for medium in release.iterfind('medium-list/medium'):
        if int(medium.findtext('position')) == pos:
            break
    for i, track in enumerate(medium.iterfind('track-list/track')):
        recording = track.find('recording')
        MBrec = Recording(recording.get("id"), int(track.findtext("position")), MBmedium, i)
        MBrec.tags.add("title", recording.findtext("title"))
        MBrec.backendUrl = BackendURL.fromString("audiocd://{0}.{1}/ripped/{0}/{1}.flac"
                                                 .format(discid, i))
    for _, MBrec in sorted(MBmedium.children.items()):
        MBrec.lookupInfo()
    MBmedium.insertWorks()
    
    if len(MBrelease.children) == 1:
        del MBrelease.children[pos]
        for p, child in MBmedium.children.items():
            MBrelease.insertChild(p, child)
    for p in list(MBrelease.children.keys()):
        if p != pos:
            del MBrelease.children[p] 
    return MBrelease.makeElements(level)
            
