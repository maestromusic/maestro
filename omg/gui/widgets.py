# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2013-2014 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtGui

from omg.core import elements

class ContainerTypeBox(QtGui.QComboBox):
    """ComboBox to select a container type."""
    
    def __init__(self, currentType=None):
        """Create the ContainerTypeBox with *currentType* selected.
        
        If *currentType* is None, there will be a "None" entry which is then also the default.
        """
        # TODO: wollen wir das wirklich?
        super().__init__()
        if currentType is None:
            self.addItem('')
        for type in elements.CONTAINER_TYPES:
            if type == elements.TYPE_CONTAINER:
                title = self.tr('(General) container')
            else:
                title = elements.getTypeTitle(type)
            icon = elements.getTypeIcon(type)
            if icon is not None:
                self.addItem(icon, title, type)
            else:
                self.addItem(title, type)
            if type == currentType:
                self.setCurrentIndex(self.count() - 1)
                
    def currentType(self):
        """Return the currently selected container type."""
        return self.itemData(self.currentIndex())
