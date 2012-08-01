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

import weakref

from . import leveltreemodel
from ..core import levels

class EditorModel(leveltreemodel.LevelTreeModel):
    
    instances = weakref.WeakSet()
    
    def __init__(self, level=levels.editor, ids=None):
        super().__init__(level, ids)
        EditorModel.instances.add(self)
    
    def loadFile(self, path):
        if path not in self.level:
            return self.level.get(path)
        else:
            id = levels.idFromPath(path)
        for model in self.instances:
            if id in model:
                return self.level.get(path)
        return self.level.reload(id)
        
        