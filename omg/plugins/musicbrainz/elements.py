# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2014 Martin Altmayer, Michael Helmling
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

from functools import reduce

from omg.core import elements, nodes, tags
from omg import logging

from .xmlapi import AliasEntity, Alias, MBTagStorage, query
from . import plugin as mbplugin

logger = logging.getLogger("musicbrainz.elements")

class MBNode(nodes.Node):
    
    def __init__(self, mbElement, parent=None):
        super().__init__()
        self.element = mbElement
        if len(mbElement.children) > 0:
            self.contents = [MBNode(elem, parent=self)
                             for _, elem in sorted(mbElement.children.items())]
        else:
            self.contents = None
        self.parent = parent
        self.position = mbElement.position
    
    def hasContents(self):
        return bool(self.contents)
    
    def title(self):
        posText = "{} - ".format(self.position) if self.position is not None else ""
        if "title" in self.element.tags:
            return posText + ", ".join(map(str, self.element.tags.get("title")))
        return posText + "<no title>"

    def __str__(self):
        return ("<{}>({})".format(self.element.__class__, self.element.tags.get("title")))
        

class MBTreeElement:
    """An item in a tree of MusicBrainz entities (as opposed to OMG elements).
    
    Attributes:
        mbid (str): The MusicBrainz ID. What kind of entity this ID refers to is not fixed.
        tags (MBTagStorage): MusicBrainz tags
        children (dict): Mapping position to child MBelement.
        parent (MBTreeElement): The parent element, if exists.
        position (int): Position
        ignore (bool): Whether the element should be ignored when creating OMG elements
    """
    def __init__(self, mbid):
        self.mbid = mbid
        self.tags = MBTagStorage()
        self.children = {}
        self.parent = None
        self.position = None
        self.ignore = False
    
    def insertChild(self, position, child):
        """Insert `child` as child on position `position` into this item.
        
        If `position` is None, it is figured automatically to be the last entry.
        """
        if position is None:
            if len(self.children) == 0:
                position = 1
            else:
                position = max(self.children.keys()) + 1
        self.children[position] = child
        child.position = position
        child.parent = self
    
    
    def __eq__(self, other):
        """Tests for equality of the *mbid* attribute."""
        return self.mbid == other.mbid
    
    
    def walk(self, includeSelf=True):
        """Recursively yield all descendant items."""
        if includeSelf:
            yield self
        for child in self.children.values():
            for subchild in child.walk():
                yield subchild
            #yield from child.walk() py3.3 version
    
    
    def assignCommonTags(self):
        """Add tags that are common in all children to the own tags."""
        children = self.children.values()
        commonTags = set(reduce(lambda x,y: x & y, [set(child.tags.keys()) for child in children]))
        commonTagValues = {}
        differentTags=set()
        for child in children:
            t = child.tags
            for tag in commonTags:
                if tag not in commonTagValues:
                    commonTagValues[tag] = t[tag]
                elif commonTagValues[tag] != t[tag]:
                    differentTags.add(tag)
        sameTags = commonTags - differentTags
        for tag in sameTags:
            for val in commonTagValues[tag]:
                if tag not in self.tags or val not in self.tags[tag]:
                    self.tags.add(tag, val)


    def makeElements(self, level, includeParentTags=True):
        """Creates a tree of OMG elements in *level* matching this MusicBrainz item."""
        elTags = self.makeOMGTags(mbplugin.tagMap, includeParentTags)
        if isinstance(self, Recording):
            elem = level.collect(self.backendUrl)
            diff = tags.TagStorageDifference(None, elTags)
            level.changeTags({elem: diff})
        else:
            contents = elements.ContentList()
            for pos, child in self.children.items():
                elem = child.makeElements(level)            
                contents.insert(pos, elem.id)
            elem = level.createContainer(tags=elTags, contents=contents, type=self.containerType)            
        elem.mbItem = self
        self.element = elem
        return elem
    
    
    def makeOMGTags(self, mapping, includeParents=True):
        omgTags = self.tags.asOMGTags(mapping)
        if includeParents:
            element = self
            while element.parent is not None:
                element = element.parent
                parentTags = element.tags.asOMGTags(mapping)
                for tag, values in parentTags.items():
                    if tag is not tags.TITLE:
                        omgTags.addUnique(tag, *values)
        return omgTags
        
    def collectAliasEntities(self):
        """Returns a set of all AliasEntity tag values of this item and all of its descendants."""
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
    
    def passTags(self, excludes):
        for tag, vals in self.tags.items():
            if tag in excludes:
                continue
            for child in self.walk(False):
                if tag not in child.tags:
                    child.tags[tag] = vals
    
    def __str__(self):
        return "{}({})".format(type(self).__name__, self.mbid if "title" not in self.tags else self.tags["title"][0])


class Release(MBTreeElement):
    """A release is the top-level container structure in MusicBrainz that we care about.
    """
    
    containerType = elements.TYPE_ALBUM
    
    def mediumForDiscid(self, discid):
        """Return the position of the medium in this release with given *discid*, if such exists.
        """
        for pos, child in self.children.items():
            if discid in child.discids:
                return pos


class Medium(MBTreeElement):
    """A medium inside a release. Usually has one or more discids associated to it."""
    
    containerType = elements.TYPE_CONTAINER
    
    def __init__(self, pos, release, discids, title=None):
        """Create the medium with associated *discids* as position *position* in *release*.
        
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
                    newChildren.append((child.position + posOffset, child.parentWork))
                    child.parentWork.insertChild(None, child)
                    child.parentWork.lookupInfo(False)
                child.parentWork = None
            else:
                newChildren.append((child.position + posOffset, child))
        self.children.clear()
        for pos, child in newChildren:
            self.insertChild(pos, child)
            if isinstance(child, Work):
                child.passTags("title")
                child.assignCommonTags()
    
    def __eq__(self, other):
        return self is other


class Recording(MBTreeElement):
    """A recording is a unique piece of recorded audio.
    
    Every track on a CD is associated to exactly one recording. Since we don't care about tracks,
    we immediately insert Recordings as children of media.
    """
    
    def __init__(self, recordingid, pos, parent, tracknumber):
        """Create recording with the given id and insert it at *position* under *parent*.
        
        Since the MusicBrainz position could theoretically be different from the tracknumber, the
        latter is needed as well.
        """
        super().__init__(recordingid)
        parent.insertChild(pos, self)
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
                          "producer" : "producer",
                          "editor" : "editor",
                          "mix" : "mixer",
                          "mastering" : "mastering"}
            
            if reltype == "instrument":
                instrument = relation.findtext("attribute-list/attribute")
                tag = "performer:"+instrument
            elif reltype in simpleTags:
                tag = simpleTags[reltype]
            elif reltype == "vocal":
                voice = relation.findtext("attribute-list/attribute")
                if voice is None:
                    tag = "vocals"
                else:
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
        

class Work(MBTreeElement):
    
    containerType = elements.TYPE_WORK
    
    def __init__(self, workid):
        super().__init__(workid)
        self.parentWork = None

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
                logger.warning("unknown work-work relation {} in {}".format(relation.get("type"), self.mbid))
