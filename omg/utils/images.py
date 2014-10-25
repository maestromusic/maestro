# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2014 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtCore, QtGui, QtSvg
from PyQt4.QtCore import Qt

_staticImages = {}


def icon(name):
    """Return a QIcon for the icon with the given name."""
    return QtGui.QIcon(":maestro/icons/" + name)

def pixmap(name):
    """Return a QPixmap for the icon with the given name."""
    return QtGui.QPixmap(":maestro/icons/" + name)


def standardIcon(name):
    style = QtGui.QApplication.style()
    qtIcons = {
        "file": QtGui.QStyle.SP_FileIcon,
        "directory": QtGui.QStyle.SP_DirIcon,
        "ok": QtGui.QStyle.SP_DialogOkButton,
        "cancel": QtGui.QStyle.SP_DialogCancelButton,
        "help": QtGui.QStyle.SP_DialogHelpButton,
        "open": QtGui.QStyle.SP_DialogOpenButton,
        "save": QtGui.QStyle.SP_DialogSaveButton,
        "close": QtGui.QStyle.SP_DialogCloseButton,
        "apply": QtGui.QStyle.SP_DialogApplyButton,
        "reset": QtGui.QStyle.SP_DialogResetButton,
        "discard": QtGui.QStyle.SP_DialogDiscardButton,
        "yes": QtGui.QStyle.SP_DialogYesButton,
        "no": QtGui.QStyle.SP_DialogNoButton, 
        "up": QtGui.QStyle.SP_ArrowUp,
        "down": QtGui.QStyle.SP_ArrowDown,
        "left": QtGui.QStyle.SP_ArrowLeft,
        "right": QtGui.QStyle.SP_ArrowRight, 
        "back": QtGui.QStyle.SP_ArrowBack,
        "forward": QtGui.QStyle.SP_ArrowForward,
    }
    if name in qtIcons:
        return style.standardIcon(qtIcons[name])
    else:
        return QtGui.QIcon()


def standardPixmap(name):
    style = QtGui.QApplication.style()
    if name in ["expander", "collapser"]:
        if name in _staticImages:
            return _staticImages[name]
        else:
            pixmap = QtGui.QPixmap(16, 12)
            pixmap.fill(Qt.transparent)
            option = QtGui.QStyleOption()
            option.type = QtGui.QStyleOption.SO_ViewItem
            option.rect = QtCore.QRect(QtCore.QPoint(0, 0), QtCore.QPoint(10, 10))
            option.state = QtGui.QStyle.State_Children
            if name == "collapser":
                option.state |=  QtGui.QStyle.State_Open
            painter = QtGui.QPainter(pixmap)
            style.drawPrimitive(QtGui.QStyle.PE_IndicatorBranch, option, painter)
            painter.end()
            _staticImages[name] = pixmap
            return pixmap
    else:
        return QtGui.QPixmap()


def html(pixmap, attributes=''):
    """Return an <img>-tag that contains the pixmap embedded into HTML using a data-URI
    (https://en.wikipedia.org/wiki/Data_URI_scheme). Use this to include pixmaps that are not stored in a
    file into HTML-code. *attributes* is inserted into the tag and may contain arbitrary HTML-attributes.
    """ 
    buffer = QtCore.QBuffer()
    pixmap.save(buffer, "PNG")
    string = bytes(buffer.buffer().toBase64()).decode('ascii')
    return '<img {} src="data:image/png;base64,{}" />'.format(attributes, string)


def renderSvg(fileOrRenderer, name, width, height, background=Qt.transparent):
    """Load the object with the given name from *file* and render it into a pixmap of the given
    dimensions. Return that pixmap."""#TODO
    if isinstance(fileOrRenderer, str):
        renderer = QtSvg.QSvgRenderer(fileOrRenderer)
    else: renderer = fileOrRenderer
    pixmap = QtGui.QPixmap(width, height)
    pixmap.fill(background)
    painter = QtGui.QPainter(pixmap)
    renderer.render(painter, name)
    painter.end()
    return pixmap
