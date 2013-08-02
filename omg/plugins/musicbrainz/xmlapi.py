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
        logger.debug("found cached MB URL {}".format(url))
        data = ans.getSingle()
    else:
        logger.debug("Querying MB URL {}".format(url))
        with req.urlopen(url) as response:
            data = response.readall()
        db.query("INSERT INTO {}musicbrainzqueries (url, xml) VALUES (?,?)".format(db.prefix), url, data)
    root = etree.fromstring(data)
    for node in root.iter(): # remove namespaces
        if node.tag.startswith('{'):
            node.tag = node.tag.rsplit('}', 1)[-1]
    return root


class MBTagStorage(dict):
    
    def __setitem__(self, key, value):
        
        if isinstance(value, str) or isinstance(value, MBArtist):
            value = [value]
        super().__setitem__(key, value)
        
    def add(self, key, value):
        if key in self:
            self[key].append(value)
        else:
            self[key] = [value]

class MBArtist:
    
    def __init__(self, node):
        self.mbid = node.get("id")
        self.name = node.findtext("name")
        self.sortName = node.findtext("sort-name")

    def __str__(self):
        return "MBArtist({})".format(self.canonicalName)


class MBTreeItem:
    
    def __init__(self, mbid):
        self.mbid = mbid
        self.tags = MBTagStorage()
        self.children = {}
        self.parent = None
        self.pos = None
        
    def insertChild(self, pos, child):
        self.children[pos] = child
        child.pos = pos
        child.parent = self
    
    def __str__(self):
        return "{}(mbid={})".format(self.__class__.__name__, self.mbid)
    
    def makeElements(self, level):
        if not isinstance(self, Recording):
            #contentList = elements.ContentList
            elements = []
            for pos, child in self.children.items():
                element = child.makeElements(level)            
                elements.append(element)
            element = level.createContainer(tags=makeOMGTags(self.tags), contents=elements)
        else:
            element = level.collect(self.backendUrl)
            diff = tags.TagStorageDifference(None, makeOMGTags(self.tags))
            level.changeTags({element: diff})        
        return element

    
class Release(MBTreeItem):
    """A release is the top-level container structure in MusicBrainz that we care about.
    """

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
        self.discids = []
    
    def insertWorks(self):
        """Inserts superworks as intermediate level between the medium and its recording.
        
        This method assumes that all childs of *self* are Recording instances.
        """
        last = None
        for pos in sorted(self.children.keys()):
            child = self.children[pos]
            if child.parentWork:
                if last and self.children[last] is child.parentWork:
                    self.children[last].insertChild(child.workpos, child)
                    del self.children[pos]
                else:
                    self.insertChild(pos, child.parentWork)
                    child.parentWork.children[child.workpos] = child
                    last = pos


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
        self.tracknumber = tracknumber
        self.work = None # associated Work instance (if any)
        
    def lookupInfo(self):
        """Queries MusicBrainz for tag information and potential related works."""
        recording = query("recording",
                          self.mbid,
                          ("artist-rels", "work-rels", "artists")
                         ).find("recording")
        for artistcredit in recording.iterfind("artist-credit"):
            for child in artistcredit:
                if child.tag == "name-credit":
                    self.tags.add("artist", MBArtist(child.find("artist")))
                else:
                    logger.warning("unknown artist-credit {} in recording {}"
                                   .format(child.tag, self.mbid))
        
        for relation in recording.iterfind('relation-list[@target-type="artist"]/relation'):
            artist = MBArtist(relation.find("artist"))
            reltype = relation.get("type")
            simpleTags = {"conductor" : "conductor",
                          "performing orchestra" : "performer:orchestra",
                          "arranger" : "arranger",
                          "chorus master" : "chorusmaster",
                          "performer" : "performer"}
            
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
        
        for relation in recording.iterfind('relation-list[@target-type="work"]/relation'):
            if relation.get("type") == "performance":
                workid = relation.findtext("target")
                work = Work(workid)
                self.work = work
                work.recording = self
                work.lookupInfo()
            else:
                logger.warning("unknown work relation '{}' in recording '{}'"
                               .format(relation.get("type"), self.mbid))
        
    def mergeWork(self):
        if self.work is None:
            self.parentWork = None
            return
        self.workid = self.work.mbid
        for tag, values in self.work.tags.items():
            if tag in self.tags:
                if tag == "title":
                    self.tags[tag] = values[:]
                else:
                    self.tags[tag].extend(values)
            else:
                self.tags[tag] = values
        self.parentWork = self.work.parentWork
        if self.parentWork:
            self.parentWork.children[self.work.pos] = self
            self.workpos = self.work.pos
        self.work = None

    def __str__(self):
        ret = super().__str__()
        if self.work:
            ret += "->recording of: {}".format(self.work)
        return ret
        

class Work(MBTreeItem):
    
    def __init__(self, workid,):
        super().__init__(workid)
        self.parentWork = None

    def lookupInfo(self):
        work = query("work", self.mbid, ("work-rels", "artist-rels")).find("work")
        addTag(self.tags, "title", work.findtext("title"))
        for relation in work.iterfind('relation-list[@target-type="artist"]/relation'):
            if relation.get("type") == "composer":
                addTag(self.tags, "composer", relation.findtext('artist/name'))
            elif relation.get("type") == "lyricist":
                addTag(self.tags, "lyricist", relation.findtext('artist/name'))
            elif relation.get("type") == "orchestrator":
                addTag(self.tags, "lyricist", relation.findtext('artist/name'))
            else:
                logger.warning("unknown work-artist relation {} in work {}"
                               .format(relation.get("type"), self.mbid))
        for relation in work.iterfind('relation-list[@target-type="work"]/relation'):
            if relation.get("type") == "parts":
                assert relation.findtext("direction") == "backward"
                assert self.parentWork is None
                parentWorkId = relation.find('work').get('id')
                # check if previous sibling has the same parent work
                try:
                    recParent = self.recording.parent
                    prevPos = max(pos for pos in recParent.children if pos < self.recording.pos)
                    prevChild = recParent.children[prevPos].work
                    if prevChild and prevChild.parentWork and prevChild.parentWork.mbid == parentWorkId:
                        self.parentWork = prevChild.parentWork
                        self.parentWork.insertChild(len(self.parentWork.children)+1, self)
                except ValueError:
                    pass
                if self.parentWork is None:
                    self.parentWork = Work(parentWorkId)
                    self.parentWork.tags["title"] = [relation.findtext('work/title')]
                    self.parentWork.insertChild(1, self)
            else:
                logger.debug("unknown work-work relation {} in {}".format(relation.get("type"), self.mbid))
        
    def __str__(self):
        if self.parentWork:
            return "{} [Pt. {} in {}]".format(self.tags['title'], self.pos, self.parentWork.tags['title'])
        return super().__str__()

        



def findReleasesForDiscid(discid):
    """Finds releases containing specified disc using MusicBrainz.
    
    Returns a list of Release objects, containing Medium objects but no
    recordings.
    """
    root = query("discid", discid, ("artists",))
    releases = []
    for release in root.iter("release"):
        mbit = Release(release.get("id"))
        title = release.find('title').text
        for medium in release.iterfind('medium-list/medium'):
            pos = int(medium.findtext('position'))
            disctitle = medium.findtext('title')
            discids = [disc.get("id") for disc in medium.iterfind('disc-list/disc')]
            theMedium = Medium(pos, mbit, discids, [disctitle] if disctitle else None)
        mbit.tags['title'] = [title]
        mbit.tags['status'] = [release.findtext('status')]
        artists = release.iterfind('artist-credit/name-credit/artist/name')
        if artists:
            mbit.tags["artist"] = [art.text for art in artists]
        if release.find('date') is not None:
            mbit.tags["date"] = [release.findtext('date')]
        if release.find('country') is not None:
            mbit.tags["country"] = [release.findtext('country')]
        if release.find('barcode') is not None:
            mbit.tags["barcode"] = [release.findtext('barcode')]
        releases.append(mbit)
    return releases
        
def makeOMGTags(mbtags):
    tag = tags.Storage()
    for key, values in mbtags.items():
        tag[tags.get(key)] = values
    return tag
    
def makeReleaseContainer(MBrelease, discid, level):
    release = query("release", MBrelease.mbid, ("recordings", "artists")).find("release")
    for pos, MBmedium in MBrelease.children.items():
        if discid in MBmedium.discids:
            break
    for medium in release.iterfind('medium-list/medium'):
        print('hurra')
        if int(medium.findtext('position')) == pos:
            break
    for i, track in enumerate(medium.iterfind('track-list/track')):
        recording = track.find('recording')
        MBrec = Recording(recording.get("id"), int(track.findtext("position")), MBmedium, i)
        MBrec.tags["title"] = [recording.findtext("title")]
        MBrec.backendUrl = BackendURL.fromString("audiocd://{}/{}".format(discid, i))
    # check if recordings are performances of works
    for _, MBrec in sorted(MBmedium.children.items()):
        MBrec.lookupInfo()
    for _, MBrec in sorted(MBmedium.children.items()):
        MBrec.mergeWork()
    MBmedium.insertWorks()
    
    if len(MBrelease.children) == 1:
        del MBrelease.children[pos]
        for p, child in MBmedium.children.items():
            MBrelease.insertChild(p, child)
    print(MBmedium.pprint())
    return MBrelease.makeElements(level)
            
