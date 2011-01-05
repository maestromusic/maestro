#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

class DynamicGridLayout(QtGui.QGridLayout):
    """This subclass of QGridLayout adds to methods to remove whole rows and to insert widgets between existing rows. If you simply remove all widgets from a QGridLayout the row will still exist, but be empty. And usually it is not possible to insert items between to (full) rows without moving all further widgets down (this is exactly what insertRow does).
    DO NOT use this class with widgets spanning several rows."""
    def __init__(self,parent=None):
        """Create a new DynamicGridLayout with the given parent."""
        QtGui.QGridLayout.__init__(self,parent)

    def removeRow(self,row):
        """Remove the given row (first row is 0) from the layout and move all further widgets a row up. Remember that you have to delete widgets or set their parents to None after removing them from a layout."""
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
        """Insert an empty row at the given pos (before the first row is 0) into the layout. Effectively this means to move beginning with that row all widgets one row down."""
        for row in range(pos,self.rowCount()):
            for column in range(self.columnCount()):
                item = self.itemAtPosition(row,column)
                if item is not None:
                    self.removeItem(item)
                    self.addItem(item,row+1,column)
