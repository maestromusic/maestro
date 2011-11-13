# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt


def createSortingTableWidgetClass(name,keyFunc):
    """Return a subclass of QtGui.QTableWidgetItem that uses *keyFunc* to compute keys during sorting.
    *keyFunc* must be a function mapping an instance of the new class to the key. Alternatively *keyFunc*
    may be one of the strings ``leadingInt`` or ``checked``. In that case one of the predefined functions of
    this module will be used.
    """
    if isinstance(keyFunc,str):
        keyFunc = {'leadingInt': leadingInt,'checked': checked}[keyFunc]
    lt = lambda self,other: keyFunc(self) < keyFunc(other)
    ge = lambda self,other: keyFunc(self) >= keyFunc(other)
    return type(name,(QtGui.QTableWidgetItem,),{'__lt__': lt, '__ge__': ge})


def leadingInt(item):
    """If the text of the QtGui.QTableWidgetItem *item* starts with an integer, return it.
    Otherwise return -1.""" 
    text = item.text()
    i = 0
    while i < len(text) and text[i].isnumeric:
        i += 1
    if i == 0:
        return -1
    else: return int(text[:i])


def checked(item):
    """Return whether the QtGui.QTableWidgetItem *item* is checked."""
    return item.checkState() == Qt.Checked
    