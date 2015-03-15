# -*- coding: utf-8 -*-
# Maestro Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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

import os.path

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
translate = QtCore.QCoreApplication.translate

from ...core import nodes
from ...models import rootedtreemodel
from ... import utils
from ...gui import delegates

class Directory(nodes.Node):
    def __init__(self, name):
        self.name = name
        self.parent = None
        self.contents = []
        self.dirCount = 0
        self.oldPath = None
        
    def files(self):
        return self.contents[self.dirCount:]
        
    def subDirectories(self):
        return self.contents[:self.dirCount] 
    
    def writeTo(self, dirPath, delete):
        path = os.path.join(dirPath, self.name)
        if not os.path.exists(path):
            os.makedirs()#TODO
        elif not os.path.isdir(path):
            raise SomeError #TODO
        
        if delete:
            newNames = [c.name for c in self.contents]
            oldNames = os.listdir(path)
            for name in set(oldNames) - set(newNames):
                os.remove(os.path.join(path, name)) #TODO remove dirs recursively
        
        for c in self.contents:
            c.writeTo(path, delete)
            
    def __str__(self):
        return self.name
        
    def find(self, name):
        for c in self.contents:
            if c.name == name:
                return c
        else: return None
        
    def sort(self):
        self.contents[:self.dirCount] = sorted(self.contents[:self.dirCount], key=lambda d: d.name)
        self.contents[self.dirCount:] = sorted(self.contents[self.dirCount:], key=lambda f: f.name)
        for dir in self.contents[:self.dirCount]:
            dir.sort()
            
    @property
    def path(self):
        parents = reversed(list(p.name for p in self.getParents(includeSelf=True, excludeRootNode=True)))
        return os.path.join(*parents)
        
    
class File(nodes.Wrapper):
    def __init__(self, name, element):
        assert element.isFile()
        super().__init__(element)
        self.name = name
        self.oldPath = None
        
    def hasContents(self):
        return False
    
    def writeTo(self, dirPath, delete=False):
        path = os.path.join(dirPath, self.name)
        if os.path.exists(path):
            try:
                # Open with filebackend
                # write tags
                return
            except:
                pass
        os.remove(path)
        shutil.copyfile(self.oldPath, path)
        # open with filebackend
        # write tags

    path = Directory.path


class RootDirectory(Directory, nodes.RootNode):
    def __init__(self, model):
        super().__init__('/')
        self.model = model
        assert model is not None
        
                
class FileTreeModel(rootedtreemodel.RootedTreeModel):
    def __init__(self):
        super().__init__(RootDirectory(self))
        self.fileCount = 0
        self.totalLength = 0
        
    def addFile(self, path, element):
        components = utils.files.splitPath(path, includeRoot=False)
        parent = self.root
        for name in components[:-1]: # without file
            dir = parent.find(name)
            if dir is None:
                dir = Directory(name)
                dir.parent = parent
                parent.contents.append(dir)
            parent = dir
        file = File(components[-1], element)
        file.parent = parent
        parent.contents.append(file)
        self.fileCount += 1
        self.totalLength += element.length
        
    def sort(self):
        self.root.sort()


class FileTreeView(QtWidgets.QTreeView):
    def __init__(self, model=None):
        super().__init__()
        self.setHeaderHidden(True)
        self.setMinimumSize(550, 600)
        self.setAlternatingRowColors(True)
        profile = FileTreeDelegate.profileType.default()
        self.setItemDelegate(FileTreeDelegate(self, profile))
        if model is None:
            model = FileTreeModel()
        self.setModel(model)
        
    def setModel(self, model):
        self.itemDelegate().model = model
        super().setModel(model)
        self.expandAll()
        
        
class FileTreeDelegate(delegates.StandardDelegate):
    profileType = delegates.profiles.createProfileType(
            name       = 'filetree',
            title      = translate("Delegates", "File Tree"),
            leftData   = [],
            rightData  = [],
            overwrite = {"fitInTitleRowData": delegates.profiles.DataPiece("length"),
                         "showFlagIcons": False,
                         "coverSize": 0,
                        }
    )
    
    def layout(self, index, availableWidth):
        node = self.model.data(index)
        
        self.addCenter(delegates.TextItem(node.name))
        if isinstance(node, File):
            self.newRow()
            super().layout(index, availableWidth)
    