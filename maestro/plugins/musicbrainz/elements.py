# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2014-2015 Martin Altmayer, Michael Helmling
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

from ...core import elements, nodes, tags, domains
from ...core.elements import ContainerType
from ... import logging, config, utils
from ...core.nodes import Wrapper

from .xmlapi import AliasEntity, MBTagStorage, query, tagsFromQuery


class ElementConfiguration:

    def __init__(self, tagMap, searchRelease=True, mediumContainer=False, forceMediumContainer=False):
        self.tagMap = tagMap
        self.searchRelease = searchRelease
        self.mediumContainer = mediumContainer
        self.forceMediumContainer = forceMediumContainer


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
        return "<{}>({})".format(self.element.__class__, self.element.tags.get("title"))
        

class MBTreeElement:
    """An item in a tree of MusicBrainz entities (as opposed to Maestro elements).
    
    Attributes:
        mbid (str): The MusicBrainz ID. What kind of entity this ID refers to is not fixed.
        tags (MBTagStorage): MusicBrainz tags
        children (dict): Mapping position to child MBelement.
        parent (MBTreeElement): The parent element, if exists.
        position (int): Position
        ignore (bool): Whether the element should be ignored when creating Maestro elements
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
            yield from child.walk()
    
    def makeElements(self, level, conf):
        """Creates a tree of Maestro elements resembling the calling :class:`MBTreeElement`.

        :param levels.Level level: Level in which to create the elements.
        :param ELementConfiguration conf: Configuration influencing the creation.
        """
        def skipMediumContainer(medium):
            if not isinstance(medium, Medium):
                return False
            if conf.forceMediumContainer:
                return False
            if not conf.mediumContainer:
                return True
            return 'title' not in medium.tags

        if conf.searchRelease and isinstance(self, Release) and tags.isInDb('musicbrainz_albumid'):
            albumid = self.mbid
            from ... import search
            from ...search.criteria import TagCriterion
            tag = tags.get('musicbrainz_albumid')
            criterion = TagCriterion(value=albumid, tagList=[tag])
            search.search(criterion)
            if len(criterion.result) == 1:
                relId = list(criterion.result)[0]
                releaseElem = level.collect(relId)
                Wrapper(releaseElem).loadContents(recursive=True)
                newChildren = [(pos, child) for (pos, child) in self.children.items() if not child.ignore]
                assert len(newChildren) == 1
                mediumPos, mediumChild = newChildren[0]
                if skipMediumContainer(mediumChild):
                    if len(releaseElem.contents) == 0:
                        firstPos = 1
                    else:
                        firstPos = releaseElem.contents.positions[-1] + 1
                    for i, child in enumerate(mediumChild.children.values()):
                        level.insertContents(releaseElem,
                                             [(firstPos + i, child.makeElements(level, conf))])
                else:
                    if mediumPos in releaseElem.contents.positions:
                        pos = releaseElem.contents.positions[-1] + 1
                    else:
                        pos = mediumPos
                    level.insertContents(releaseElem, [(pos, mediumChild.makeElements(level, conf))])
                return releaseElem
        elTags = self.tags.asMaestroTags(conf.tagMap)
        elTags.add(*self.idTag())
        if isinstance(self, Recording):
            elem = level.collect(self.backendUrl)
            diff = tags.TagStorageDifference(None, elTags)
            level.changeTags({elem: diff})
        else:
            contents = elements.ContentList()
            for pos, child in self.children.items():
                if not child.ignore:
                    if skipMediumContainer(child):
                        for ppos, cchild in child.children.items():
                            elem = cchild.makeElements(level, conf)
                            contents.insert(ppos, elem.id)
                    else:
                        elem = child.makeElements(level, conf)
                        contents.insert(pos, elem.id)
            elem = level.createContainer(tags=elTags, contents=contents, type=self.containerType,
                                         domain=domains.domainByName(config.options.musicbrainz.domain))
        return elem
    
    def assignCommonTags(self):
        """Add tags that are common in all children to the own tags."""
        children = self.children.values()
        commonTags = set(reduce(lambda x,y: x & y, [set(child.tags.keys()) for child in children]))
        if 'title' in commonTags:
            commonTags.remove('title')
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

    def collectExternalTags(self):
        etags = set()
        for item in self.walk():
            for tag in item.tags:
                if not tags.isInDb(tag):
                    etags.add(tag)
        return etags
    
        
    def idTag(self):
        return self.idTagName, self.mbid
    
    def passTags(self, excludes):
        for tag, vals in self.tags.items():
            if tag in excludes:
                continue
            for child in self.walk(False):
                for val in vals:
                    child.tags.add(tag, val)
    
    def __str__(self):
        return "{}({})".format(type(self).__name__, self.mbid if "title" not in self.tags else self.tags["title"][0])


class Release(MBTreeElement):
    """A release is the top-level container structure in MusicBrainz that we care about.
    """
    
    containerType = ContainerType.Album
    idTagName = 'musicbrainz_albumid'
    
    def mediumForDiscid(self, discid):
        """Find the medium in this release hat has id `discid`, and return a tuple consisting of
        the medium's position and the medium itself. 
        """
        for pos, child in self.children.items():
            if discid in child.discids:
                return pos, child


class Medium(MBTreeElement):
    """A medium inside a release. Usually has one or more discids associated to it."""
    
    containerType = ContainerType.Container
    idTagName = 'musicbrainz_discid'
    
    def __init__(self, pos, release, discids, title=None):
        """Create the medium with associated *discids* as position *position* in *release*.
        
        It will be inserted into *release* at the given position. *discids* is a list of disc
        IDs associated to that medium.
        If the medium has a title, that may be given as will. It will be inserted into the
        medium's tags as "title".
        """
        super().__init__(mbid=None)
        release.insertChild(pos, self)
        if title:
            self.tags.add("title", title)
        self.discids = set(discids)
    
    def idTag(self):
        try:
            return self.idTagName, self.currentDiscid
        except AttributeError:
            return self.idTagName, next(iter(self.discids))
    
    def insertWorks(self):
        """Inserts parent works as intermediate level between the medium and its recording.
        
        This method assumes that all children of *self* are :class:`Recording` instances.
        """
        newChildren = []
        posOffset = 0
        children = [child for pos, child in sorted(self.children.items())]
        for i, child in enumerate(children):
            inserted = False
            if child.parentWork:
                if i > 0 and children[i-1].parentWork and children[i-1].parentWork == child.parentWork:
                    newChildren[-1][1].insertChild(None, child)
                    posOffset -= 1
                    inserted = True
                elif i < len(children) - 1 and children[i+1].parentWork and children[i+1].parentWork == child.parentWork:
                    newChildren.append((child.position + posOffset, child.parentWork))
                    child.parentWork.insertChild(None, child)
                    child.parentWork.lookupInfo(False)
                    inserted = True
                # child.parentWork = None
            if not inserted:
                newChildren.append((child.position + posOffset, child))
        self.children.clear()
        for pos, child in newChildren:
            self.insertChild(pos, child)
            if isinstance(child, Work):
                child.tags['album'] = child.tags['title'][:]
                child.passTags(['title'])
                child.assignCommonTags()
                # remove common prefix on children tags
                children = child.children.values()
                titles = [str(elem.tags['title'][0]) for elem in children]
                shortTitles = utils.strings.removeCommonPrefixAndNumbers(titles)
                for c, t in zip(children, shortTitles):
                    if isinstance(c.tags['title'][0], AliasEntity):
                        c.tags['title'][0].name = t
                    else:
                        c.tags['title'][0] = t
    
    def __eq__(self, other):
        return self is other


class Recording(MBTreeElement):
    """A recording is a unique piece of recorded audio.
    
    Every track on a CD is associated to exactly one recording. Since we don't care about tracks,
    we immediately insert Recordings as children of media.
    """
    
    idTagName = 'musicbrainz_trackid'
    
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
        for tag, value in tagsFromQuery(recording):
            self.tags.add(tag, value)
        for relation in recording.iterfind(
                'relation-list[@target-type="work"]/relation[@type="performance"]'):
            if self.workid:
                logging.warning(__name__, 'more than one work relation in {}'.format(self.mbid))
                break
            work = Work(relation.findtext('target'))
            date = relation.findtext('begin')
            if date:
                self.tags.add('date', date)
            work.lookupInfo()
            self.mergeWork(work)
        
    def mergeWork(self, work):
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
    
    containerType = ContainerType.Work
    
    idTagName = 'musicbrainz_workid'
    
    def __init__(self, workid):
        super().__init__(workid)
        self.parentWork = None

    def lookupInfo(self, works=True):
        incs = ["artist-rels"] + (["work-rels"] if works else [])
        work = query("work", self.mbid, incs).find("work")
        ent = AliasEntity.get(work)
        ent.asTag.add("title")
        self.tags['title'] = ent
        for tag, value in tagsFromQuery(work):
            self.tags.add(tag, value)
        for relation in work.iterfind('relation-list[@target-type="work"]/relation[@type="parts"]'):
            if relation.findtext("direction") == 'backward' and not self.parentWork:
                parentWorkId = relation.find('work').get('id')
                self.parentWork = Work(parentWorkId)

