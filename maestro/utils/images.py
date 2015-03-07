# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2014-2015 Martin Altmayer, Michael Helmling
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

from PyQt5 import QtCore, QtGui, QtWidgets, QtSvg
from PyQt5.QtCore import Qt

namedPixmaps = {} 
namedIcons = {
    'flag': 'flag_blue.png', # generic flag icon
}
_fallbacks = {}


def icon(name):
    """Return a QIcon. *name* may be
        - a name: a name from utils.images.namedIcons or from
                http://standards.freedesktop.org/icon-naming-spec/icon-naming-spec-latest.html
        - a filepath: paths must be relative to the images/icons/-folder and contain an extension.
    """
    if '.' in name:
        return QtGui.QIcon(':maestro/icons/' + name)
    elif name in namedIcons:
        return QtGui.QIcon(':maestro/icons/' + namedIcons[name])
    elif name in _fallbacks:
        return QtGui.QIcon.fromTheme(name, _fallbacks[name])
    else:
        return QtGui.QIcon.fromTheme(name)


def pixmap(name):
    """Return a QPixmap. *name* may be either a filepath (relative to images-folder) or name from
    utils.images.namedPixmaps. Additionally the special names 'expander' and 'collapser' are supported.
    They will return the platform-specific pixmap to expand/collapse items in QTreeViews.
    """
    if '.' in name:
        return QtGui.QPixmap(':maestro/' + name)
    elif name in namedPixmaps:
        return QtGui.QPixmap(':maestro/' + namedPixmaps[name])
    elif name in ['expander', 'collapser']:
        pixmap = QtGui.QPixmap(16, 12)
        pixmap.fill(Qt.transparent)
        option = QtWidgets.QStyleOption()
        option.type = QtWidgets.QStyleOption.SO_ViewItem
        option.rect = QtCore.QRect(QtCore.QPoint(0, 0), QtCore.QPoint(10, 10))
        option.state = QtWidgets.QStyle.State_Children
        if name == 'collapser':
            option.state |=  QtWidgets.QStyle.State_Open
        painter = QtGui.QPainter(pixmap)
        style = QtWidgets.QApplication.style()
        style.drawPrimitive(QtWidgets.QStyle.PE_IndicatorBranch, option, painter)
        painter.end()
        namedPixmaps[name] = pixmap
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
    dimensions. Return that pixmap."""
    if isinstance(fileOrRenderer, str):
        renderer = QtSvg.QSvgRenderer(fileOrRenderer)
    else: renderer = fileOrRenderer
    pixmap = QtGui.QPixmap(width, height)
    pixmap.fill(background)
    painter = QtGui.QPainter(pixmap)
    renderer.render(painter, name)
    painter.end()
    return pixmap
