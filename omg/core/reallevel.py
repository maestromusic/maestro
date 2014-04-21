# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2012-2014 Martin Altmayer, Michael Helmling
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

import itertools

from . import elements, levels, tags, flags, domains
from .. import application, database as db, filebackends, stack


# The ids of all elements that are in the database and have been loaded to some level 
_dbIds = set()

class RealFileEvent(application.ChangeEvent):
    
    _attrs = ("modified", "added", "removed", "renamed", "deleted")
    
    def __init__(self, **kwargs):
        super().__init__()
        for attr, iterable in kwargs.items():
            if not attr in self._attrs:
                raise ValueError("Invalid keyword attribute for {}: {}".format(type(self), attr))
            setattr(self, attr, set(iterable))
    
    def __getattr__(self, attr):
        if attr in self._attrs:
            return set()
        raise AttributeError("'{}' has no attribute '{}'".format(type(self), attr))
    
    def merge(self, other):
        if not type(other) is type(self):
            return False
        for attr in self._attrs:
            attrInOther = getattr(other, attr)
            if len(attrInOther) > 0:
                if len(getattr(self, attr)) > 0:
                    getattr(self, attr).update(getattr(other, attr))
                else:
                    setattr(self, attr, attrInOther)
        # transfer renamings to modified and added
        for ( old, new ) in self.renamed:
            if old in self.modified:
                self.modified.add(new)
                self.modified.remove(old)
        return True
    
    def __str__(self):
        return "RealFileEvent({})".format(", ".join(("{}={}".format(attr, getattr(self, attr))
                                                     for attr in self._attrs)))
            
        
class RealLevel(levels.Level):
    """The real level, comprising the state of database and filesystem.
    
    Changes made here do not only change the element objects but also the database and, if
    files are affected, the filesystem state.
    """
    
    def __init__(self):
        super().__init__('REAL', None)
        self.filesystemDispatcher = application.ChangeEventDispatcher(stack.stack)
    
    def emitFilesystemEvent(self, **kwArgs):
        """Simple shortcut to emit a FileSystemEvent."""
        stack.addEvent(self.filesystemDispatcher, RealFileEvent(**kwArgs))
        
    def collect(self, param):
        self._ensureLoaded([param])
        return self[param]
    
    def collectMany(self, params):
        # We need to iterate params twice
        if not isinstance(params, (list, tuple)):
            params = list(params)
        self._ensureLoaded(params)
        return [self[param] for param in params]
    
    # The difference between fetch, _fetch and collect is only important on levels below real.
    fetch = collect
    _fetch = collect
    fetchMany = collectMany
    get = collect #TODO deprecated
    
    def _ensureLoaded(self, params):
        # note that __contains__ (p not in self) ensures that p is either int or url 
        ids = [p for p in params if isinstance(p, int) and p not in self]
        urls = []
        for p in params:
            if isinstance(p, filebackends.BackendURL) and p not in self:
                id = db.idFromUrl(p)
                if id is not None:
                    ids.append(id)
                else: urls.append(p)
                
        if len(ids) > 0:
            # this will silently ignore ids which are not found in the DB
            self.loadFromDb(ids)
        if len(urls) > 0:
            self.loadFromUrls(urls)
        if any(p not in self for p in params):
            # This means that an element could not be loaded (e.g. params contains the id of a new container
            # which only exists on the editor level).
            raise levels.ElementGetError(self, [p for p in params if p not in self])
     
    def loadFromDb(self, idList, level=None):
        """Load elements specified by *idList* from the database into *level* which defaults to the
        real level."""
        if level is None:
            level = self
            
        if len(idList) == 0: # queries will fail otherwise
            return []
        
        csIdList = db.csList(idList)
        
        # bare elements
        result = db.query("""
                SELECT el.domain, el.id, el.file, el.type, f.url, f.length
                FROM {0}elements AS el LEFT JOIN {0}files AS f ON el.id = f.element_id
                WHERE el.id IN ({1})
                """.format(db.prefix, csIdList))
        for domainId, id, file, elementType, url, length in result:
            _dbIds.add(id)
            if file:
                level.elements[id] = elements.File(domains.domainById(domainId), level, id,
                                                   url = filebackends.BackendURL.fromString(url),
                                                   length = length,
                                                   type = elementType)
            else:
                level.elements[id] = elements.Container(domains.domainById(domainId), level, id,
                                                        type=elementType)
                
        # contents
        result = db.query("""
                SELECT el.id, c.position, c.element_id
                FROM {0}elements AS el JOIN {0}contents AS c ON el.id = c.container_id
                WHERE el.id IN ({1})
                ORDER BY position
                """.format(db.prefix, csIdList))
        for id, pos, contentId in result:
            level.elements[id].contents.insert(pos, contentId)
            
        # parents
        result = db.query("""
                SELECT el.id, c.container_id
                FROM {0}elements AS el JOIN {0}contents AS c ON el.id = c.element_id
                WHERE el.id IN ({1})
                """.format(db.prefix, csIdList))
        for id, contentId in result:
            level.elements[id].parents.append(contentId)
            
        # tags
        result = db.query("""
                SELECT el.id, t.tag_id, t.value_id
                FROM {0}elements AS el JOIN {0}tags AS t ON el.id = t.element_id
                WHERE el.id IN ({1})
                """.format(db.prefix, csIdList))
        for id, tagId, valueId in result:
            tag = tags.get(tagId)
            level.elements[id].tags.add(tag, db.valueFromId(tag, valueId))
            
        # flags
        result = db.query("""
                SELECT el.id, f.flag_id
                FROM {0}elements AS el JOIN {0}flags AS f ON el.id = f.element_id
                WHERE el.id IN ({1})
                """.format(db.prefix, csIdList))
        for id, flagId in result:
            level.elements[id].flags.append(flags.get(flagId))
            
        # stickers
        result = db.query("""
                SELECT element_id, type, data
                FROM {}stickers
                WHERE element_id IN ({})
                ORDER BY element_id, type, sort
                """.format(db.prefix, csIdList))
        # This is a bit complicated because the stickers should be stored in tuples, not lists
        # Changing the lists would break undo/redo
        #TODO: is this really necessary?
        current = None
        buffer = []
        for (id, type, sticker) in result:
            if current is None:
                current = (id, type)
            elif current != (id, type):
                level.elements[current[0]].stickers[current[1]] = tuple(buffer)
                current = (id, type)
                buffer = []
            element = level.elements[id]
            if element.stickers is None:
                element.stickers = {}
            buffer.append(sticker)
        if current is not None:
            level.elements[current[0]].stickers[current[1]] = tuple(buffer)
        
        try:
            return [self.elements[id] for id in idList]
        except KeyError: # probably some ids were not contained in the database
            raise levels.ElementGetError(self, [id for id in idList if id not in self])
            
    def loadFromUrls(self, urls, level=None):
        """Loads files given by *urls*, into *level* which defaults to the real level. This must not be
        used for elements which are contained in the database."""
        if level is None:
            level = self
        result = []
        for url in urls:
            backendFile = url.getBackendFile()
            backendFile.readTags()
            fTags = backendFile.tags
            fLength = backendFile.length
            if db.idFromUrl(url) is not None:
                raise RuntimeError("loadFromURLs called on '{}', which is in DB.".format(url))
            id = levels.idFromUrl(url, create=True)
            domain = url.source.domain if url.source is not None else None
            elem = elements.File(domain, level, id, url=url, length=fLength, tags=fTags)
            elem.specialTags = backendFile.specialTags           
            level.elements[id] = elem
            result.append(elem)
        return result
    
    def _commitHelper(self, elements):
        """Helper function called by Level.commit() if the parent level is real."""
        
        # First load all missing files so that everything is avaliable on real
        for element in elements:
            if element.isFile() and element.id not in self:
                self.collect(element.id if element.isInDb() else element.url)
        
        # AGENDA:
        # 1. Collect data
        # 2. Write file tags (do this first because it is most likely to fail). Private tags must
        #    be excluded first, because files have not yet been added to the database. Tags must be
        #    changed before adding files to the db, because files on real might contain external
        #    tags.
        # 3. Add elements to database
        # 4. Change remaining tags (i.e. container tags and private tags)
        
        # 1. Collect data
        addToDbElements = [] # Have to be added to the db (this does overlap oldElements below)
        fileTagChanges = {}
        remainingTagChanges = {}
        for file in filter(lambda e: e.isFile(), elements):
            inReal = self[file.id]
            if file.isInDb():
                newTags = file.tags.copy()
            else:
                addToDbElements.append(inReal)
                if file.tags.containsPrivateTags():
                    newTags = file.tags.withoutPrivateTags()
                    remainingTagChanges[inReal] = tags.TagDifference(
                                            additions=list(file.tags.privateTags().getTuples()))
                else:
                    newTags = file.tags.copy()
            if inReal.tags != newTags:
                fileTagChanges[inReal] = tags.TagStorageDifference(inReal.tags, newTags)
        for container in filter(lambda e: e.isContainer(), elements):
            if container.isInDb():
                inReal = self[container.id]
                remainingTagChanges[inReal] = tags.TagStorageDifference(inReal.tags,
                                                                        container.tags.copy())
            else:
                addToDbElements.append(container.copy(level=self))
                # we do not have to change tags of new containers
                    
        # 2.-4.
        try:
            self.changeTags(fileTagChanges)
        except (filebackends.TagWriteError, OSError) as e:
            stack.abortMacro()
            raise e
        self.addToDb(addToDbElements)
        self.changeTags(remainingTagChanges)
    
    
    # =============================================================
    # Overridden from Level: these methods modify DB and filesystem
    # =============================================================
    def commit(self, elements=None):
        raise RuntimeError("Cannot commit real level.")
    
    
    def addElements(self, elements):
        if not all(element.isContainer() for element in elements):
            raise ValueError("On real level addElements may only be used for containers.")
        self.addToDb(elements)

    def removeElements(self, elements):
        if not all(element.isContainer() for element in elements):
            raise ValueError("On real level removeElements may only be used for containers.")
        self.removeFromDB(elements)
        
    # These are used by the super class implementations of addElements and removeElements
    def _addElements(self): raise NotImplementedError()
    def _removeElements(self): raise NotImplementedError()
    
    def addToDb(self, elements):
        """Add the given elements to the database including their tags, flags, stickers and contents.
        Remarks:
        
            - element.level must be this level,
            - files must already be loaded on real, containers must not,
            - this method will not change the elements but assume that in particular their parent-lists
              are correct (on the real level).
        
        """
        if len(elements):
            assert all(element.level is self for element in elements)
            stack.push(self.tr("Add elements to database"),
                       stack.Call(self._addToDb, elements),
                       stack.Call(self._removeFromDb, elements))
        
    def removeFromDb(self, elements):
        """Remove the given elements with all their tags etc. from the database. Containers are also
        removed from the real level. No element may be contained in any container unless this container
        is also in *elements*.
        """
        if len(elements):
            stack.push(self.tr("Remove elements from database"),
                       stack.Call(self._removeFromDb, elements),
                       stack.Call(self._addToDb, elements))
    
    def _addToDb(self, elements):
        """Like addToDb but not undoable."""
        if len(elements) == 0:
            return # multiquery will fail otherwise
        
        for element in elements:
            assert not element.isInDb()
            assert element.level is self
            if element.id not in self:
                assert element.isContainer()
                self.elements[element.id] = element
            else: assert element.isFile() 
        
        db.transaction()
        
        data = [(element.domain.id if element.domain is not None else None,
                 element.id,
                 element.isFile(),
                 element.type if element.isContainer() else 0,
                 len(element.contents) if element.isContainer() else 0)
                        for element in elements]
        db.multiQuery("INSERT INTO {p}elements (domain, id, file, type, elements) VALUES (?,?,?,?,?)", data)

        # Do this early, otherwise e.g. setFlags might raise a ConsistencyError)
        _dbIds.update(element.id for element in elements)
            
        for element in elements:
            # Set tags
            db.query("DELETE FROM {p}tags WHERE element_id = ?", element.id)
            for tag in element.tags:
                db.multiQuery("INSERT INTO {p}tags (element_id,tag_id,value_id) VALUES (?,?,?)",
                      [(element.id, tag.id, db.idFromValue(tag, value, insert=True))
                       for value in element.tags[tag]])
            
            # Set flags
            db.query("DELETE FROM {p}flags WHERE element_id = ?", element.id)
            if len(element.flags) > 0:
                db.multiQuery("INSERT INTO {p}flags (element_id, flag_id) VALUES (?,?)",
                              [(element.id, flag.id) for flag in element.flags])

            # Set stickers
            db.query("DELETE FROM {p}stickers WHERE element_id = ?", element.id)
            for type, values in element.stickers.items():
                db.multiQuery("INSERT INTO {p}stickers (element_id, type, sort, data) VALUES (?,?,?,?)",
                              [(element.id, type, i, val) for i, val in enumerate(values)])
                
        newFiles = [element for element in elements if element.isFile()]
        if len(newFiles) > 0:
            from .. import filesystem
            db.multiQuery("INSERT INTO {p}files (element_id, url, hash, length) VALUES (?,?,?,?)",
                          ((element.id, str(element.url), filesystem.getNewfileHash(element.url),
                            element.length) for element in newFiles))
            self.emitFilesystemEvent(added=(f for f in newFiles if f.url.scheme == "file"))
        
        contentData = []
        for element in elements:
            if element.isContainer():
                contentData.extend((element.id, item[0], item[1]) for item in element.contents.items())
                for childId in element.contents:
                    if element.id not in self[childId].parents:
                        self[childId].parents.append(element.id)
                        
        if len(contentData) > 0:
            db.multiQuery("INSERT INTO {p}contents (container_id, position, element_id) VALUES (?,?,?)",
                          contentData)
                                      
        db.commit()
        self.emit(levels.LevelChangedEvent(dbAddedIds=[el.id for el in elements]))
                
    def _removeFromDb(self, elements):
        """Like removeFromDb but not undoable."""
        for element in elements:
            assert element.isInDb()
            if element.isContainer():
                del self.elements[element.id]
                for childId in element.contents:
                    self[childId].parents.remove(element.id)
        _dbIds.difference_update(element.id for element in elements)
        
        # Rely on foreign keys to delete all tags, flags etc. from the database
        ids = itertools.chain.from_iterable(element.contents for element in elements
                                                             if element.isContainer())
        db.query("DELETE FROM {}elements WHERE id IN ({})"
                 .format(db.prefix, db.csList(element.id for element in elements)))
        removedFiles = [element.url for element in elements if element.isFile()
                                                            and element.url.scheme == "file"]
        if len(removedFiles) > 0:
            self.emitFilesystemEvent(removed=removedFiles)
        self.emit(levels.LevelChangedEvent(dbRemovedIds=[el.id for el in elements]))
        
    def deleteElements(self, elements, fromDisk=False):
        elements = list(elements)
        stack.beginMacro("delete elements")
        # 1st step: isolate the elements (remove contents & parents)
        for element in elements:
            if element.isContainer() and len(element.contents) > 0:
                self.removeContents(element, element.contents.positions)
            if len(element.parents) > 0:
                for parentId in element.parents:
                    parent = self.collect(parentId)
                    self.removeContents(parent, parent.contents.positionsOf(id=element.id))
        self.removeFromDb([element for element in elements if element.isInDb()])
        stack.endMacro()
        if fromDisk and any(element.isFile() for element in elements):
            for element in elements:
                if element.isFile():
                    element.url.getBackendFile().delete()
            stack.clear()

    def _changeTags(self, changes, dbOnly=False):
        if not dbOnly:
            filebackends.changeTags(changes) # might raise TagWriteError
        
        dbChanges = {el: diffs for el, diffs in changes.items() if el.isInDb()}
        if len(dbChanges) > 0:
            db.transaction()
            dbRemovals = [(el.id, tag.id, db.idFromValue(tag, value))
                          for el, diff in dbChanges.items()
                          for tag, value in diff.getRemovals() if tag.isInDb()]
            if len(dbRemovals):
                db.multiQuery("DELETE FROM {p}tags WHERE element_id=? AND tag_id=? AND value_id=?",
                              dbRemovals)
                
            dbAdditions = [(el.id, tag.id, db.idFromValue(tag, value, insert=True))
                           for el, diff in dbChanges.items()
                           for tag, value in diff.getAdditions() if tag.isInDb()]
            if len(dbAdditions):
                db.multiQuery("INSERT INTO {p}tags (element_id, tag_id, value_id) VALUES (?,?,?)",
                              dbAdditions)
            files = [ (elem.id, ) for elem in dbChanges if elem.isFile() ]
            if len(files) > 0:
                db.multiQuery("UPDATE {p}files SET verified=CURRENT_TIMESTAMP WHERE element_id=?",
                              files)
            db.commit()
        super()._changeTags(changes)
        
    def _changeFlags(self, changes):
        if not all(element.isInDb() for element in changes.keys()):
            raise levels.ConsistencyError("Elements on real must be added to the DB before adding tags.")
        db.transaction()
        dbRemovals = [(el.id, flag.id) for el, diff in changes.items() for flag in diff.getRemovals()]
        if len(dbRemovals):
            db.multiQuery("DELETE FROM {p}flags WHERE element_id = ? AND flag_id = ?",
                          dbRemovals)
        dbAdditions = [(el.id, flag.id) for el, diff in changes.items() for flag in diff.getAdditions()]
        if len(dbAdditions):
            db.multiQuery("INSERT INTO {p}flags (element_id, flag_id) VALUES(?,?)",
                          dbAdditions)
        db.commit()
        super()._changeFlags(changes)
            
    def _changeStickers(self, changes):
        if not all(element.isInDb() for element in changes.keys()):
            raise levels.ConsistencyError("Elements on real must be added to the DB before adding stickers.")
        db.transaction()
        for element, diff in changes.items():
            for type, (a, b) in diff.diffs.items():
                if a is not None:
                    db.query("DELETE FROM {p}stickers WHERE type=? AND element_id=?",
                             type, element.id)
                if b is not None:
                    db.multiQuery("INSERT INTO {p}stickers (element_id, type, sort, data) VALUES (?,?,?,?)",
                                  [(element.id, type, i, val) for i, val in enumerate(b)])
        db.commit()
        super()._changeStickers(changes)
                
    def _setStickers(self, type, elementToStickers):
        if not all(element.isInDb() for element in elementToStickers.keys()):
            raise levels.ConsistencyError("Elements on real must be added to the DB before adding stickers.")
        values = []
        for element, stickers in elementToStickers.items():
            if stickers is not None:
                values.extend((element.id, type, i, s) for i, s in enumerate(stickers))
        db.transaction()
        db.query("DELETE FROM {}stickers WHERE type = ? AND element_id IN ({})"
                 .format(db.prefix, db.csIdList(elementToStickers.keys())), type)
        if len(values) > 0:
            db.multiQuery("INSERT INTO {p}stickers (element_id, type, sort, data) VALUES (?,?,?,?)",
                          values)
        db.commit()
        super()._setStickers(type, elementToStickers)
        
    def _setTypes(self, containerTypes):
        if len(containerTypes) > 0:
            db.multiQuery("UPDATE {p}elements SET type = ? WHERE id = ?",
                          ((type, c.id) for c, type in containerTypes.items()))
            super()._setTypes(containerTypes)
    
    def _setContents(self, parent, contents):
        db.transaction()
        db.query("DELETE FROM {p}contents WHERE container_id = ?", parent.id)
        #Note: This checks skips elements which are not loaded on real. This should rarely happen and
        # due to foreign key constraints...
        if not all(self[childId].isInDb() for childId in contents if childId in self):
            raise levels.ConsistencyError("Elements must be in the DB before being added to a container.")
        
        if len(contents) > 0:
            # ...the following query will fail anyway (but with a DBException)
            # if some contents are not in the database yet.
            db.multiQuery("INSERT INTO {p}contents (container_id, position, element_id) VALUES (?,?,?)",
                          [(parent.id, pos, childId) for pos, childId in contents.items()])
        db.updateElementsCounter((parent.id,))
        db.commit()
        super()._setContents(parent, contents)

    def _insertContents(self, parent, insertions):
        if not all(element.isInDb() for _, element in insertions):
            raise levels.ConsistencyError("Elements must be in the DB before being added to a container.")
        db.transaction()
        db.multiQuery("INSERT INTO {p}contents (container_id, position, element_id) VALUES (?,?,?)",
                      [(parent.id, pos, child.id) for pos, child in insertions])
        db.updateElementsCounter((parent.id,))
        db.commit()
        super()._insertContents(parent, insertions)
        
    def _removeContents(self, parent, positions):
        db.transaction()
        db.multiQuery("DELETE FROM {p}contents WHERE container_id=? AND position=?",
                      [(parent.id, pos) for pos in positions])
        db.updateElementsCounter((parent.id,))
        db.commit()
        super()._removeContents(parent, positions)
    
    def _changePositions(self, parent, changes):
        super()._changePositions(parent, changes)
        changes = list(changes.items())
        changesOne = [ (newPos, parent.id, oldPos)
                        for (oldPos, newPos) in sorted(changes, key=lambda cng: cng[1], reverse=True)
                        if newPos > oldPos ]
        changesTwo = [ (newPos, parent.id, oldPos)
                        for (oldPos, newPos) in sorted(changes, key=lambda chng: chng[1])
                        if newPos < oldPos ]
        for data in changesOne, changesTwo:
            db.multiQuery("UPDATE {p}contents SET position=? WHERE container_id=? AND position=?", data)
    
    def _renameFiles(self, renamings):
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
        db.multiQuery("UPDATE {p}files SET url=? WHERE element_id=?",
                      [ (str(newUrl), element.id) for element, (_, newUrl) in renamings.items() ])
        super()._renameFiles(renamings)
