# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
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

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt


class DynamicGridLayout(QtGui.QGridLayout):
    """This subclass of QGridLayout adds two methods to remove whole rows and to insert widgets between 
    existing rows. If you simply remove all widgets from a QGridLayout the rows will still exist, but be
    empty. And usually it is not possible to insert items between two (full) rows without moving all further
    widgets down (this is exactly what the insertRow-method of this class does).
    
    DO NOT use this class with widgets spanning several rows.
    """
    def __init__(self,parent=None):
        """Create a new DynamicGridLayout with the given parent."""
        QtGui.QGridLayout.__init__(self,parent)

    def removeRow(self,row):
        """Remove the given row (first row is 0) from the layout and move all further widgets a row up.
        Remember that you have to delete widgets or set their parents to None after removing them from a 
        layout.
        """
        # First remove all items from the row
        for column in range(self.columnCount()):
            item = self.itemAtPosition(row,column)
            if item is not None:
                self.removeItem(item)

        # Then move all items in further rows up:
        for r in range(row+1,self.rowCount()):
            for column in range(self.columnCount()):
                item = self.itemAtPosition(r,column)
                if item is not None:
                    self.removeItem(item)
                    self.addItem(item,r-1,column)

    def insertRow(self,pos):
        """Insert an empty row at the given *pos* (before the first row is 0) into the layout. Effectively
        this means to move beginning with that row all widgets one row down."""
        for row in range(pos,self.rowCount()):
            for column in range(self.columnCount()):
                item = self.itemAtPosition(row,column)
                if item is not None:
                    self.removeItem(item)
                    self.addItem(item,row+1,column)
