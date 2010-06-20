#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from PyQt4 import QtCore

from omg import tags, database, covers
db = database.get()

class Node:
    """(Abstract) base class for elements in a RootedTreeModel...that is almost everything in playlists, browser etc.. Node implements the methods required by RootedTreeModel using self.contents as the list of children and self.parent as parent, but does not create these variables. Subclasses must either self.contents and self.parent or overwrite the methods."""
    
    def hasChildren(self):
        """Return whether this node has at least one child node or None if it is unknown."""
        return len(self.contents) > 0
        
    def getChildren(self):
        """Return the list of children."""
        return self.contents
    
    def getChildrenCount(self):
        """Return the number of children or None if it is unknown."""
        return len(self.contents)
    
    def getParent(self):
        """Return the parent of this element."""
        return self.parent
    
    def isFile(self):
        """Return whether this node holds a file. Note that this is in general not the opposite of isContainer as e.g. rootnodes are neither."""
        return False
    
    def isContainer(self):
        """Return whether this node holds a container. Note that this is in general not the opposite of isFile as e.g. rootnodes are neither."""
        return False
        
    
# Methods to access the list of files at the end of the treemodel.
class FilelistMixin:
    def getAllFiles(self):
        assert self.contents is not None
        if self.isFile():
            yield self
        else:
            for element in self.contents:
                for file in element.getAllFiles():
                    yield file
                        
    def fileCount(self):
        assert self.contents is not None
        if self.isFile():
            return 1
        else: return sum(element.fileCount() for element in self.contents)
        
    def getFileByIndex(self,index):
        assert self.contents is not None
        index = int(index)
        if index < 0:
            raise IndexError("Index {0} is out of bounds".format(index))
        if index == 0 and self.isFile():
            return self
        else: 
            for element in self.contents:
                fileCount = element.fileCount()
                if index < fileCount:
                    return element.getFileByIndex(index)
                else: index = index - fileCount
            raise IndexError("Index {0} is out of bounds".format(index))
    
    def getIndexInFilelist(self):
        if self.getParent() is None:
            return 0
        else:
            index = self.getParent().getIndexInFilelist()
            for child in self.getParent().getChildren():
                if child == self:
                    return index
                else: index = index + child.fileCount()
            raise ValueError("FilelistMixin.getIndexInFilelist: Node {0} is not contained in its parent {1}."
                                .format(self,self.getParent()))

            
class IndexMixin:
    def index(self,node):
        for i in range(0,len(self.contents)):
            if self.contents[i] == node:
                return i
        raise ValueError("IndexMixin.index: Node {0} is not contained in element {1}.".format(node,self))
        
    def find(self,node):
        for i in range(0,len(self.contents)):
            if self.contents[i] == node:
                return i
        return -1

        
class Element(Node,FilelistMixin,IndexMixin):
    """Base class for elements (files or containers) in playlists, browser, etc.. Contains methods to load tags and contents from the database and to get the path, cover, length etc.."""
    tags = None # tags.Storage to store the tags. None until they are loaded
    contents = None # list of contents. None until they are loaded; [] if this element has no contents
    path = None # path of this Element, use getPath
    
    def __init__(self,id):
        """Initialize this element with the given id, which must be an integer."""
        assert isinstance(id,int)
        self.id = id
        
    def hasChildren(self):
        """Return whether this node has at least one child node or None if it is unknown since the contents are not loaded yet."""
        return self.contents is not None and len(self.contents) > 0
    
    def getChildrenCount(self):
        """Return the number of children or None if it is unknown since the contents are not loaded yet."""
        if self.contents is None:
            return 0
        else: return len(self.contents)
        
    def isFile(self):
        """Return whether this Element holds a file or None if it is unknown since the contents are not loaded yet."""
        if self.contents is None:
            return None
        else: return len(self.contents) == 0
    
    def isContainer(self):
        """Return whether this Element holds a container or None if it is unknown since the contents are not loaded yet."""
        if self.contents is None:
            return None
        else: return len(self.contents) > 0
        
    def getPath(self):
        """Return the path of this Element and cache it for subsequent calls. If the element has no path (e.g. containers), a ValueError is raised."""
        if self.path is None:
            self.path = db.query("SELECT path FROM files WHERE container_id = {0}".format(self.id)).getSingle()
            if self.path is None:
                raise ValueError("The element with id {0} has no path. Maybe it is a container.".format(self.id))
        return self.path
    
    def getTitle(self):
        """Return a title of this element which is created from the title-tags. If this element does not contain a title-tag some dummy-title is returned."""
        if self.tags is None:
            self.loadTags()
        if tags.TITLE in self.tags:
            return " - ".join(self.tags[tags.TITLE])
        else: return '<Kein Titel>'
        
    def loadContents(self,recursive=False,table="containers"):
        """Delete the stored contents-list and fetch the contents from the database. You may use the <table>-parameter to restrict the child elements to a specific table: The table with name <table> must contain a column 'id' and this method will only fetch elements which appear in that column. If <recursive> is true loadContents will be called recursively for all child elements."""
        self.contents = []
        result = db.query("""
                SELECT contents.element_id
                FROM contents JOIN {0} ON contents.container_id = {1} AND contents.element_id = {0}.id
                ORDER BY contents.position
                """.format(table,self.id)).getSingleColumn()
        for id in result:
            self.contents.append(Element(id))
        if recursive:
            for element in self.contents:
                element.loadContents(recursive,table)


    def loadTags(self,recursive=False,tagList=None):
        self.tags = tags.Storage()
        
        if tagList is not None:
            additionalWhereClause = " AND tag_id IN ({0})".format(",".join(str(tag.id) for tag in tagList))
        else: additionalWhereClause = ''
        
        result = db.query("""
            SELECT tag_id,value_id 
            FROM tags
            WHERE container_id = {0} {1}
            """.format(self.id,additionalWhereClause))
        for row in result:
            tag = tags.get(row[0])
            self.tags[tag].append(tag.getValue(row[1]))
        if recursive:
            for element in self.contents:
                element.loadTags(recursive,tagList)
    
    def ensureTagsAreLoaded(self):
        """Load tags if they are not loaded yet."""
        if self.tags is None:
            self.loadTags()
        
    def ensureContentsAreLoaded(self):
        """Load contents if they are not loaded yet."""
        if self.contents is None:
            self.loadContents()
    
    def getLength(self):
        """Return the length of this element. If it is a container, return the sum of the lengths of all its contents. If the length can't be computed, None is returned. This happens for example if the contents have not been loaded yet."""
        if self.contents is None:
            return None
        if len(self.contents) == 0:
            return db.query("SELECT length FROM files WHERE container_id = {0}".format(self.id)).getSingle()
        else:
            try:
                return sum(element.getLength() for element in self.contents)
            except TypeError: # At least one element does not know its length
                return None

    def getCover(self,size=None,cache=True):
        """Get this container's cover with <size>x<size> pixels or the large version if <size> is None. If <cache> is True, this method will store the cover in this Element-instance. Warning: Subsequent calls of this method will return the stored cover only if <cache> is again True."""
        if cache:
            try:
                return self._covers[size]
            except AttributeError: pass
            except KeyError: pass
        cover = covers.getCover(self,size)
        if cache:
            if not hasattr(self,"_covers"):
                self._covers = {}
            self._covers[size] = cover
        return cover
    
    # Misc
    #====================================================
    def __str__(self):
        if self.tags is not None:
            return "<Element {0}>".format(self.getTitle())
        else: return "<Element {0}>".format(self.id)