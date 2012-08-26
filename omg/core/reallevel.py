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
            urls = [levels.tIdManager(id) for id in notFound if id < 0]
            if len(positiveIds) > 0:
                self.loadFromDB(positiveIds, child)
            if len(urls) > 0:
                self.loadURLs(urls, child)
            
    def loadFromDB(self, idList, level):
        """Load elements specified by *idList* from the database into *level*."""
        if len(idList) == 0: # queries will fail otherwise
            return 
        idList = db.csList(idList)
        
        # bare elements
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
                
        # contents
        result = db.query("""
                SELECT el.id, c.position, c.element_id
                FROM {0}elements AS el JOIN {0}contents AS c ON el.id = c.container_id
                WHERE el.id IN ({1})
                ORDER BY position
                """.format(db.prefix, idList))
        for (id, pos, contentId) in result:
            level.elements[id].contents.insert(pos, contentId)
            
        # parents
        result = db.query("""
                SELECT el.id,c.container_id
                FROM {0}elements AS el JOIN {0}contents AS c ON el.id = c.element_id
                WHERE el.id IN ({1})
                """.format(db.prefix, idList))
        for (id, contentId) in result:
            level.elements[id].parents.append(contentId)
            
        # tags
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
            if fPosition is not None:
                elem.filePosition = fPosition            
            level.elements[id] = elem
    
    def setFileTagsAndRename(self, files):
        """Undoably set tags and URLs of the given files as they are in the object. Do not alter the
        database."""
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
            publicTags = file.tags.withoutPrivateTags()
            if len(publicTags) > 0:
                diff = tags.TagStorageDifference(backendFile.tags, publicTags)
                tagChanges[file] = diff
        if len(tagChanges) > 0:
            inverseChanges = {elem:diff.inverse() for elem,diff in tagChanges.items()}
            command = levels.GenericLevelCommand(redoMethod=filebackends.changeTags,
                                          redoArgs={"changes" : tagChanges},
                                          undoMethod=filebackends.changeTags,
                                          undoArgs={"changes": inverseChanges},
                                          text=self.tr("change tags"),
                                          errorClass=TagWriteError)
            self.stack.push(command)
            if command.error:
                raise command.error
            
    # =============================================================
    # Overridden from Level: these methods modify DB and filesystem
    # =============================================================
    def _elementToDBHelper(self, element):
        db.write.setTags(element.id, element.tags)
        db.write.setFlags(element.id, element.flags)
        db.write.setData(element.id, element.data)
        db.write.setContents(element.id, element.contents)
        
    def _createContainer(self, tags, flags, data, major, contents, id=None):
        if id is not None:
            raise ValueError("Don't call _createContainer with an ID on real!")
        db.transaction()
        id = db.write.createElements([ (False, True, 0, major) ])
        element = super()._createContainer(tags, flags, data, major, contents, id)
        self._elementToDBHelper(element)
        db.commit()
        return element
    
    def _addElement(self, element):
        super()._addElement(element)
        db.transaction()
        db.write.createElementsWithIds([(element.id, element.isFile(), len(element.parents) == 0,
                                          len(element.contents), element.major)])
        self._elementToDBHelper(element)
        db.commit()
        
    def _removeElement(self, element):
        super()._removeElement(element)
        db.write.deleteElements([element.id])
        
    def _insertContents(self, parent, insertions, emitEvent=True):
        db.write.addContents([(parent.id, pos, child.id) for pos, child in insertions])
        super()._insertContents(parent, insertions, emitEvent)
        
    def _removeContents(self, parent, positions, emitEvent=True):
        db.write.removeContents([(parent.id, pos) for pos in positions])
        super()._removeContents(parent, positions, emitEvent)
       
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
    
    def _changePositions(self, parent, changes, emitEvent=True):
        super()._changePositions(parent, changes, emitEvent)
        db.write.changePositions(parent.id, list(changes.items()))
    
    def _changeTags(self, changes, emitEvent=True):
        """Change tags of elements. Might raise a TagWriteError if files are involved. If an error is raised,
        any changes made before are undone.
        """
        filebackends.changeTags(changes) # might raise TagWriteError
        
        db.transaction()
        dbRemovals = [(el.id,tag.id,db.idFromValue(tag,value))
                      for el,diff in changes.items() for tag,value in diff.getRemovals() if tag.isInDB()]
        if len(dbRemovals):
            db.multiQuery("DELETE FROM {}tags WHERE element_id=? AND tag_id=? AND value_id=?"
                          .format(db.prefix),dbRemovals)
            
        dbAdditions = [(el.id,tag.id,db.idFromValue(tag,value,insert=True))
                       for el,diff in changes.items() for tag,value in diff.getAdditions() if tag.isInDB()]
        if len(dbAdditions):
            db.multiQuery("INSERT INTO {}tags (element_id,tag_id,value_id) VALUES (?,?,?)"
                          .format(db.prefix),dbAdditions)
        db.commit()
        super()._changeTags(changes, emitEvent)
        
    def _changeFlags(self, changes, emitEvent=True):
        db.transaction()
        dbRemovals = [(el.id,flag.id) for el,diff in changes.items() for flag in diff.getRemovals()]
        if len(dbRemovals):
            db.multiQuery("DELETE FROM {}flags WHERE element_id = ? AND flag_id = ?".format(db.prefix),
                          dbRemovals)
        dbAdditions = [(el.id,flag.id) for el,diff in changes.items() for flag in diff.getAdditions()]
        if len(dbAdditions):
            db.multiQuery("INSERT INTO {}flags (element_id,flag_id) VALUES(?,?)".format(db.prefix),
                          dbAdditions)
        db.commit()
        super()._changeFlags(changes, emitEvent)
            
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
        