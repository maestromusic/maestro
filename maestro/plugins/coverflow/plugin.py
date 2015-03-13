# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2015 Martin Altmayer, Michael Helmling
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

from PyQt5 import QtCore, QtGui

translate = QtCore.QCoreApplication.translate

from maestro.core import covers, levels, nodes
from maestro.gui import selection
from maestro.widgets.playlist import gui
from maestro.widgets.browser import coverbrowser

try:
    import imageflow
except ImportError:
    raise ImportError("imageflow module not installed. See https://github.com/MartinAltmayer/imageflow/")


def enable():
    coverbrowser.addDisplayClass('coverflow', CoverFlowWidget)

def disable():
    coverbrowser.removeDisplayClass('coverflow')
    

class CoverFlowWidget(imageflow.ImageFlowWidget):
    """Subclass of ImageFlowWidget that implements coverbrowser.AbstractCoverBrowser and some additional
    event handling."""
    selectionChanged = QtCore.pyqtSignal()
    
    def __init__(self, data, parent=None):
        super().__init__(data, parent=parent)
        self.indexChanged.connect(self.selectionChanged)
        self.imageDblClicked.connect(self._handleDoubleClicked)
        
    @classmethod
    def getTitle(cls):
        return translate("CoverFlow", "Cover flow")
    
    def selection(self):
        cover = self.currentImage()
        if cover is not None:
            return selection.Selection.fromElements(levels.real, [levels.real.collect(cover.elid)])
        else: return None
    
    state = imageflow.ImageFlowWidget.saveData
    
    def setCovers(self, ids, coverPaths):
        images = [imageflow.Image(os.path.join(covers.COVER_DIR, coverPaths[id])) for id in ids]
        for id, image in zip(ids, images):
            image.elid = id
        self.setImages(images)    
        
    def startDrag(self, cover):
        drag = QtGui.QDrag(self)
        element = levels.real.collect(cover.elid)
        drag.setMimeData(selection.MimeData.fromElements(levels.real, [element]))
        drag.setPixmap(element.getCover(100))
        drag.setHotSpot(QtCore.QPoint(50, 50))
        drag.exec_()
        
    def _handleDoubleClicked(self, cover):
        wrapper = nodes.Wrapper(levels.real.collect(cover.elid))
        wrapper.loadContents(recursive=True)
        gui.appendToDefaultPlaylist([wrapper])
    