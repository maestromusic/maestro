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

#TODO: if this module remains that empty. Move everything into application

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ..application import ChangeEvent
from .. import logging


translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)


stack = QtGui.QUndoStack()


class ChangeEventDispatcher(QtCore.QObject):
    
    changes = QtCore.pyqtSignal(ChangeEvent)
    
    def __init__(self):
        QtCore.QObject.__init__(self)

dispatcher = ChangeEventDispatcher()
 
        
def _debugAll(event):
    logger.debug("EVENT: " + str(event))
    
dispatcher.changes.connect(_debugAll)
