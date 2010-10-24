#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtCore

indicesChanged = None
_instance = None

class DatabaseChangeNotice():
    
    tags = True # indicate if tags of element have changed
    contents = True # indicate if contents of element have changed
    deleted = False # indicate if element was deleted
    created = False # indicate if element has been newly created
    ids = None # the affected element_ids
    recursive = True # changes also affect subcontainers
    
    def __init__(self, ids, tags = True, contents = True, cover = False, recursive = True, deleted = False, created = False):
        if isinstance(ids,int):
            self.ids = [ids]
        else: self.ids = ids
        self.tags = tags
        self.contents = contents
        self.recursive = recursive
        self.deleted = deleted
        self.created = created
        self.cover = cover
        
    @staticmethod
    def deleteNotice(ids, recursive = False):
        """Convenience function."""
        return DatabaseChangeNotice(ids, tags = False, contents = False, cover = False, recursive = recursive, deleted = True, created = False)
        
class DBUpdateDistributor(QtCore.QObject):
    
    indicesChanged = QtCore.pyqtSignal(DatabaseChangeNotice)
    
    def __init__(self):
        QtCore.QObject.__init__(self)
        

def init():
    assert _instance is None
    global _instance,indicesChanged
    _instance = DBUpdateDistributor()
    indicesChanged = _instance.indicesChanged
