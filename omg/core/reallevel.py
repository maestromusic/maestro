# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2012 Martin Altmayer, Michael Helmling
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

from . import elements, levels, tags, flags
from .. import database as db
from ..database import write
from .. import filebackends
from .. import logging

logger = logging.getLogger(__name__)


class RealLevel(levels.Level):
    """The real level, comprising the state of database and filesystem.
    
    Changes made here do not only change the element objects but also the database and, if
    files are affected, the filesystem state.
    """
    
    def __init__(self):
        super().__init__('REAL', None)
        # This hack makes the inherited implementations of get and load work with the overwritten
        # implementation of loadIntoChild
        self.parent = self
    
    def loadIntoChild(self, ids, child):
        """Loads IDs which are not yet known from database (if positive) or filesystem (else)."""
        notFound = []
        for id in ids:
            if id in self.elements:
                child.elements[id] = self.elements[id].copy()
                child.elements[id].level = child
            else: notFound.append(id)
        if len(notFound) > 0:
            positiveIds = [id for id in notFound if id > 0]
            urls = [ levels.tIdManager(id) for id in notFound if id < 0 ]
            if len(positiveIds) > 0:
                self.loadFromDB(positiveIds, child)
            if len(urls) > 0:
                self.loadURLs(urls, child)
            
    def loadFromDB(self, idList, level):
        """Load elements specified by *idList* from the database into *level*."""
        if len(idList) == 0: # queries will fail otherwise
            return 
        idList = ','.join(str(id) for id in idList)
        #  bare elements
        result = db.query("""
                SELECT el.id, el.file, el.major, f.url, f.length
                FROM {0}elements AS el LEFT JOIN {0}files AS f ON el.id = f.element_id
                WHERE el.id IN ({1})
                """.format(db.prefix, idList))
        for (id, file, major, url, length) in result:
            if file:
                level.elements[id] = elements.File(level, id,
                                          url=filebackends.BackendURL.fromString(url),
                                          length=length)
            else:
                level.elements[id] = elements.Container(level, id, major=major)
        #  contents
        result = db.query("""
                SELECT el.id, c.position, c.element_id
                FROM {0}elements AS el JOIN {0}contents AS c ON el.id = c.container_id
                WHERE el.id IN ({1})
                ORDER BY position
                """.format(db.prefix, idList))
        for (id, pos, contentId) in result:
            level.elements[id].contents.insert(pos, contentId)
        #  parents
        result = db.query("""
                SELECT el.id,c.container_id
                FROM {0}elements AS el JOIN {0}contents AS c ON el.id = c.element_id
                WHERE el.id IN ({1})
                """.format(db.prefix, idList))
        for (id, contentId) in result:
            level.elements[id].parents.append(contentId)
        #  tags
        result = db.query("""
                SELECT el.id,t.tag_id,t.value_id
                FROM {0}elements AS el JOIN {0}tags AS t ON el.id = t.element_id
                WHERE el.id IN ({1})
                """.format(db.prefix, idList))
        for (id,tagId,valueId) in result:
            tag = tags.get(tagId)
            level.elements[id].tags.add(tag, db.valueFromId(tag, valueId))
        # flags
        result = db.query("""
                SELECT el.id,f.flag_id
                FROM {0}elements AS el JOIN {0}flags AS f ON el.id = f.element_id
                WHERE el.id IN ({1})
                """.format(db.prefix, idList))
        for (id, flagId) in result:
            level.elements[id].flags.append(flags.get(flagId))
        # data
        result = db.query("""
                SELECT element_id,type,data
                FROM {}data
                WHERE element_id IN ({})
                ORDER BY element_id,type,sort
                """.format(db.prefix, idList))
        # This is a bit complicated because the data should be stored in tuples, not lists
        # Changing the lists would break undo/redo
        current = None
        buffer = []
        for (id, type, data) in result:
            if current is None:
                current = (id, type)
            elif current != (id, type):
                level.elements[current[0]].data[current[1]] = tuple(buffer)
                current = (id,type)
                buffer = []
            element = level.elements[id]
            if element.data is None:
                element.data = {}
            buffer.append(data)
        if current is not None:
            level.elements[current[0]].data[current[1]] = tuple(buffer)
            
    def loadURLs(self, urls, level):
        """Loads files given by *urls*, into *level*."""
        for url in urls:
            backendFile = url.getBackendFile()
            backendFile.readTags()
            fTags = backendFile.tags
            fLength = backendFile.length
            fPosition = backendFile.position
            id = db.idFromUrl(url)
            if id is None:
                id = levels.tIdManager.tIdFromUrl(url)
                flags = []
            else:
                flags = db.flags(id)
                # TODO: Load private tags!
                logger.warning("loadFromURLs called on '{}', which is in DB. Are you "
                           " sure this is correct?".format(url))
            elem = elements.File(level, id=id, url=url, length=fLength, tags=fTags, flags=flags)
            elem.fileTags = fTags.copy()
            if fPosition is not None:
                elem.filePosition = fPosition            
            level.elements[id] = elem
    
    def saveTagsToFileSystem(self, elements):
        """Helper function to store the tags of *elements* on the filesystem."""
        failedElements = []
        for element in elements:
            if not element.isFile():
                continue
            try:
                real = element.url.getBackendFile()
                real.tags = element.tags.withoutPrivateTags()
                real.saveTags()
            except IOError as e:
                logger.error("Could not save tags of '{}'.".format(element.path))
                logger.error("Error was: {}".format(e))
                failedElements.append(elements)
                continue
        return failedElements
    
    def setFileTagsAndRename(self, files):
        """Undoably set tags and URLs of the files *elements* as they are in the object.
        
        Does not alter the database."""
        urlChanges = {}
        for file in files:
            if file.url != levels.tIdManager(file.id):
                urlChanges[file] = (levels.tIdManager(file.id), file.url)
        if len(urlChanges) > 0:
            self.renameFiles(urlChanges)
        tagChanges = {}
        for file in files:
            #  check if tags are different
            backendFile = file.url.getBackendFile()
            backendFile.readTags()
            diff = tags.TagDifference(backendFile.tags, file.tags)
            if not diff.onlyPrivateChanges():
                tagChanges[file] = diff
        if len(tagChanges) > 0:
            self.changeTags(tagChanges, filesOnly=True)

        
    # =============================================================
    # Overridden from Level: these methods modify DB and filesystem
    # =============================================================
    
    def _insertContents(self, parent, insertions):
        db.write.addContents([(parent.id, pos, child.id) for pos, child in insertions])
        super()._insertContents(parent, insertions)
        
    def _removeContents(self, parent, positions):
        db.write.removeContents([(parent.id, pos) for pos in positions])
        super()._removeContents(parent, positions)
    
    def _addTagValue(self, tag, value, elements, emitEvent=True):
        super()._addTagValue(tag, value, elements, emitEvent=False)
        failedElements = self.saveTagsToFileSystem(elements)
        #TODO: Correct failedElements
        dbElements = [el.id for el in elements if el.isInDB() and not el in failedElements]
        if len(dbElements):
            db.write.addTagValues(dbElements, tag, [value])
        if emitEvent:
            self.emitEvent([element.id for element in elements])
            
    def _removeTagValue(self, tag, value, elements, emitEvent=True):
        super()._removeTagValue(tag, value, elements, emitEvent=False)
        failedElements = self.saveTagsToFileSystem(elements)
        #TODO: Correct failedElements
        dbElements = [el.id for el in elements if el.isInDB() and not el in failedElements]
        if len(dbElements) > 0:
            db.write.removeTagValuesById(dbElements, tag, db.idFromValue(tag, value))
        else: assert all(element.id < 0 for element in elements)
        if emitEvent:
            self.emitEvent([element.id for element in elements])

    def _changeTagValue(self, tag, oldValue, newValue, elements, emitEvent=True):
        super()._changeTagValue(tag, oldValue, newValue, elements, emitEvent=False)
        failedElements = self.saveTagsToFileSystem(elements)
        #TODO: Correct failedElements
        dbElements = [el.id for el in elements if el.isInDB() and not el in failedElements]
        if len(dbElements):
            db.write.changeTagValueById(dbElements, tag, db.idFromValue(tag, oldValue),
                                       db.idFromValue(tag, newValue, insert=True))
        if emitEvent:
            self.emitEvent([element.id for element in elements])
    
    def _changeTags(self, changes, emitEvent=True, filesOnly=False):
        """CHange tags of elements. Might raise a TagWriteError if files are involved.
        
        If an error is raised, any changes made before are undone.
        The optional *filesOnly* suppresses any changes to the database."""
        doneFiles = []
        rollback = False
        problems = None
        for element, diff in changes.items():
            if not element.isFile():
                continue
            backendFile = element.url.getBackendFile()
            if backendFile.readOnly:
                problemUrl = element.url
                rollback = True
                break
            backendFile.readTags()
            curBTags = backendFile.tags.copy()
            diff.apply(backendFile.tags, includePrivate=False)
            logger.debug('changing tags of {}: {}'.format(element.url, diff))
            problems = backendFile.saveTags()
            if len(problems) > 0:
                problemUrl = element.url
                backendFile.tags = curBTags
                backendFile.saveTags()
                rollback = True
            else:
                doneFiles.append(element)
        if rollback:
            for elem in doneFiles:
                backendFile = element.url.getBackendFile()
                backendFile.readTags()
                changes[elem].revert(backendFile.tags, includePrivate=False)
                backendFile.saveTags()
            raise levels.TagWriteError(problemUrl, problems)
        if filesOnly:
            return
        db.transaction()
        for element, diff in changes.items():
            if not element.isInDB():
                continue
            for tag, values in diff.additions:
                if not tag.isInDB():
                    continue
                db.write.addTagValues(element.id, tag, values)
            for tag, values in diff.removals:
                if not tag.isInDB():
                    continue
                db.write.removeTagValues(element.id, tag, values)
        db.commit()
        super()._changeTags(changes, emitEvent)

    def _renameFiles(self, renamings, emitEvent=True):
        """On the real level, files are renamed both on disk and in DB."""
        doneFiles = []
        try:
            for elem, (oldUrl, newUrl) in renamings.items():
                oldUrl.getBackendFile().rename(newUrl)
                doneFiles.append(elem)
        except OSError as e:
            # rollback changes and throw error
            for elem in doneFiles:
                oldUrl, newUrl = renamings[elem]
                newUrl.getBackendFile().rename(oldUrl)
            raise levels.RenameFilesError(oldUrl, newUrl, str(e))
        db.write.changeUrls([ (element.id, str(newUrl)) for element, (_, newUrl) in renamings.items() ])
        super()._renameFiles(renamings, emitEvent)
            
    def _addFlag(self, flag, elements, emitEvent=True):
        super()._addFlag(flag, elements, emitEvent=False)
        ids = [element.id for element in elements]
        db.write.addFlag(ids, flag)
        if emitEvent:
            self.emitEvent(ids)
            
    def _removeFlag(self, flag, elements, emitEvent=True):
        super()._removeFlag(flag, elements, emitEvent=False)
        ids = [element.id for element in elements]
        db.write.removeFlag(ids, flag)
        if emitEvent:
            self.emitEvent(ids)
    
    def _changeData(self, changes, emitEvent):
        super()._changeData(changes, emitEvent)
        db.transaction()
        for element, diff in changes.items():
            for type, (a, b) in diff.diffs.items():
                if a is not None:
                    db.query("DELETE FROM {}data WHERE type=? AND element_id=?"
                             .format(db.prefix), type, element.id)
                if b is not None:
                    db.multiQuery("INSERT INTO {}data (element_id, type, sort, data) VALUES (?,?,?,?)"
                                  .format(db.prefix), [(element.id, type, i, val) for i, val in enumerate(b)])
        db.commit()
                
    def _setData(self, type, elementToData):
        super()._setData(type, elementToData)
        values = []
        for element, data in elementToData.items():
            if data is not None:
                values.extend((element.id, type, i, d) for i, d in enumerate(data))
        db.transaction()
        db.query("DELETE FROM {}data WHERE type = ? AND element_id IN ({})"
                 .format(db.prefix,db.csIdList(elementToData.keys())),type)
        if len(values) > 0:
            db.multiQuery("INSERT INTO {}data (element_id,type,sort,data) VALUES (?,?,?,?)"
                          .format(db.prefix),values)
        db.commit()
        
    def _setMajorFlags(self, elemToMajor, emitEvent=True):
        super()._setMajorFlags(elemToMajor, emitEvent)
        db.write.setMajor((el.id,major) for (el, major) in elemToMajor.items() )