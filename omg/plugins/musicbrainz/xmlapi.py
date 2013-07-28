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
from omg.utils import FlexiDate
from omg import logging

logger = logging.getLogger("musicbrainz.xmlapi")

ns = "{http://musicbrainz.org/ns/mmd-2.0#}"
baseUrl = "http://musicbrainz.org/ws/2"

class MusicBrainzItem:
    
    def __init__(self, itemtype, mbid):
        self.mbid = mbid
        self.itemtype = itemtype
        self.tags = {}
        self.children = {}
        self.parent = None
        self.pos = None
        
    def insertChild(self, pos, child):
        self.children[pos] = child
        child.pos = pos
        child.parent = self
    
    def __str__(self):
        return "{}<id={}>".format(self.itemtype, self.mbid)
    
    def textOut(self, indent=0):
        lines = [str(self)]
        for tname, tvals in self.tags.items():
            lines.append("{} = {}".format(tname, ", ".join(tvals)))
        for pos, child in self.children.items():
            lines.append("  {}.".format(pos))
            lines.extend(child.textOut(indent+2))
        return [" "*indent + line for line in lines]

    def pprint(self):
        return "\n".join(self.textOut())
    
class Release(MusicBrainzItem):
    
    def __init__(self, releaseid):
        super().__init__("release", releaseid)

class Medium(MusicBrainzItem):
    
    def __init__(self, pos, release, title=None):
        super().__init__("medium", None)
        release.insertChild(pos, self)
        if not title:
            title = ["Disc {}".format(pos)]
        self.tags["title"] = title
        self.discids = []
    
    def insertWorks(self):
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
            

def addTag(dct, key, val):
    if key not in dct:
        dct[key] = [val]
    else:
        dct[key].append(val)   


class Recording(MusicBrainzItem):
    
    def __init__(self, recordingid, pos, parent):
        super().__init__("recording", recordingid)
        parent.insertChild(pos, self)
        self.work = None
    
    def lookupInfo(self):
        logger.debug("querying recording {}".format(self.mbid))
        recording = query("recording", self.mbid, ("artist-rels", "work-rels", "artists")).find("recording")
        for artist in recording.iterfind("artist-credit/name-credit/artist/name"):
            addTag(self.tags, "artist", artist.text)
        for relation in recording.iterfind('relation-list[@target-type="artist"]/relation'):
            artist = relation.findtext("artist/name")
            reltype = relation.get("type")
            if reltype == "instrument":
                instrument = relation.findtext("attribute-list/attribute")
                tag = "performer:"+instrument
            elif reltype == "conductor":
                tag = "conductor"
            elif reltype == "performing orchestra":
                tag = "performer:orchestra"
            elif reltype == "arranger":
                tag = "arranger"
            elif reltype == "chorus master":
                tag = "chorusmaster"
            elif reltype == "vocal":
                voice = relation.findtext("attribute-list/attribute")
                if voice.startswith("soprano"):
                    tag = "performer:soprano"
                elif voice.startswith("mezzo-soprano"):
                    tag = "performer:mezzo-soprano"
                elif voice.startswith("tenor"):
                    tag = "performer:tenor"
                elif voice.startswith("baritone"):
                    tag = "performer:baritone"
                elif voice == "choir vocals":
                    tag = "performer:choir"
                else:
                    logger.warning("unknown voice: {} in {}".format(voice, self.mbid))
            elif reltype == "performer":
                tag = "performer"
            else:
                logger.warning("unknown artist relation '{}' in recording '{}'"
                               .format(relation.get("type"), self.mbid))
                continue
            addTag(self.tags, tag, artist)
        for relation in recording.iterfind('relation-list[@target-type="work"]/relation'):
            if relation.get("type") == "performance":
                workid = relation.findtext("target")
                Work(workid, self).lookupInfo()
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
        

class Work(MusicBrainzItem):
    
    def __init__(self, workid, recording=None):
        super().__init__("work", workid)
        self.parentWork = None
        if recording:
            self.recording = recording
            recording.work = self

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

        
def query(resource, mbid, includes=[]):
    
    url = "{}/{}/{}".format(baseUrl, resource, mbid)
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


def findReleasesForDiscid(discid):
    root = query("discid", discid, ("artists",))
    releases = []
    for release in root.iter("release"):
        mbit = Release(release.get("id"))
        title = release.find('title').text
        for medium in release.iterfind('medium-list/medium'):
            pos = int(medium.findtext('position'))
            disctitle = medium.findtext('title')
            theMedium = Medium(pos, mbit, [disctitle] if disctitle else None)
            theMedium.discids = [disc.get("id") for disc in medium.iterfind('disc-list/disc')]
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
        
def makeReleaseContainer(MBrelease, discid, level):
    release = query("release", MBrelease.mbid, ("recordings", "artists")).find("release")
    for pos, MBmedium in MBrelease.children.items():
        if discid in MBmedium.discids:
            break
    for medium in release.iterfind('medium-list/medium'):
        print('hurra')
        if int(medium.findtext('position')) == pos:
            break
    for track in medium.iterfind('track-list/track'):
        recording = track.find('recording')
        MBrec = Recording(recording.get("id"), int(track.findtext("position")), MBmedium)
        MBrec.tags["title"] = [recording.findtext("title")]
    # check if recordings are performances of works
    for _, MBrec in sorted(MBmedium.children.items()):
        MBrec.lookupInfo()
    for pos, MBrec in sorted(MBmedium.children.items()):
        MBrec.mergeWork()
    MBmedium.insertWorks()
    return MBrelease
            
    
def findReleases(recordingId):
    """Given a recording id, return the IDs of all releases that contain the denoted recording."""
    root = query("recording", recordingId, ("releases",))
    return [release.get("id") for release in root.iter("{}release".format(ns))]


def lookupRelease(releaseId):
    root = query("release", releaseId, ("artists", "release-groups", "recordings"))
    release = root.find(ns+"release")
    titles = [title.text for title in release.findall(ns+"title")]
    artists = [nc.find(ns+"artist").find(ns+"name").text
               for nc in release.find(ns+"artist-credit").findall(ns+"name-credit")]
    date = FlexiDate(*release.find(ns+"date").text.split("-"))
    ml = release.find(ns+"medium-list")
    tracks = {}
    for medium in ml.findall(ns+"medium"):
        discnum = int(medium.find(ns+"position").text)
        if discnum not in tracks:
            tracks[discnum] = {}
        tracklist = medium.find(ns+"track-list")
        for track in tracklist.findall(ns+"track"):
            position = int(track.find(ns+"position").text)
            recording = track.find(ns+"recording")
            tracks[discnum][position] = recording.get("id")
    print("*** found a release ***")
    print("titles={}".format(titles))
    print("artists={}".format(artists))
    print("date={}".format(date))
    print("tracks:")
    for discnum, contents in tracks.items():
        print("disc {}".format(discnum))
        for pos, recid in contents.items():
            print("  track {}: {}".format(pos, recid)) 
    return root