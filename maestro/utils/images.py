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
    'actions-export': 'actions-export.svgz',
    'accessories-text-editor': 'accessories-text-editor.svgz',
    'album': 'media-optical-audio.svgz',
    'applications-development': 'applications-development.svgz',
    'audio-x-synchronized': 'audio-x-synced.svgz',
    'audio-x-unsynchronized': 'audio-x-unsynced.svgz',
    'audio-x-generic': 'audio-x-generic.svgz',
    'browser': 'widgets/browser.svgz',
    'collection': 'collection.svgz',
    'configure-shortcuts': 'configure-shortcuts.svgz',
    'container': 'container.svgz',
    'document-edit': 'document-edit.svgz',
    'document-save': 'document-save.svgz',
    'drive-harddisk': 'drive-harddisk.svgz',
    'edit-clear': 'edit-clear.svgz',
    'edit-clear-list': 'edit-clear-list.svgz',
    'edit-clear-locationbar-rtl': 'edit-clear-locationbar-rtl.svgz',
    'edit-delete': 'edit-delete.svgz',
    'edit-rename': 'edit-rename.svgz',
    'edit-undo': 'edit-undo.svgz',
    'edit-redo': 'edit-redo.svgz',
    'edit-find': 'edit-find.svgz',
    'go-next': 'go-next.svgz',
    'go-previous': 'go-previous.svgz',
    'filesystembrowser': 'widgets/filesystembrowser.svgz',
    'flag': 'flag.svgz',  # generic flag icon
    'folder': 'folder.svgz',
    'folder-synchronized': 'folder-synced.svgz',
    'folder-unsynchronized': 'folder-unsynced.svgz',
    'help-about': 'help-about.svgz',
    'list-add': 'list-add.svgz',
    'list-remove': 'list-remove.svgz',
    'media-playback-start': 'media-playback-start.svgz',
    'preferences-delegates': 'preferences/delegates.svgz',
    'preferences-domains': 'preferences/domains.svgz',
    'preferences-profiles': 'preferences/profiles.svgz',
    'preferences-plugin': 'preferences/plugin.svgz',
    'preferences-sound': 'preferences/sound.svgz',
    'preferences-other': 'preferences/preferences.svgz',
    'recursive': 'recursive.svgz',
    'synchronized': 'dialog-ok-apply.svgz',
    'tag': 'tag.svgz',  # generic tag icon
    'tageditor': 'widgets/tageditor.svgz',
    'unsynchronized': 'dialog-warning.svgz',
    'view-media-playlist': 'widgets/view-media-playlist.svgz',
    'view-refresh': 'view-refresh.svgz',
    'work': 'work.svgz',
}
cachedIcons = {}


def icon(name):
    """Return a QIcon. *name* may be
        - a name: a name from utils.images.namedIcons
        - a filepath: paths must be relative to the images/icons/-folder and contain an extension.
    """
    if name is None:
        return QtGui.QIcon()
    if name not in cachedIcons:
        if '.' in name:
            theIcon = QtGui.QIcon(':maestro/icons/' + name)
        elif name in namedIcons:
            theIcon = QtGui.QIcon(':maestro/icons/' + namedIcons[name])
        else:
            raise ValueError('icon name {} not found'.format(name))
        cachedIcons[name] = theIcon
    return cachedIcons[name]





def pixmap(name):
    """Return a QPixmap. *name* may be either a filepath (relative to images-folder) or name from
    utils.images.namedPixmaps. Additionally the special names 'expander' and 'collapser' are supported.
    They will return the platform-specific pixmap to expand/collapse items in QTreeViews.
    """
    if '.' in name:
        return QtGui.QPixmap(':maestro/' + name)
    elif name in ['expander', 'collapser']:
        if name in namedPixmaps:
            return namedPixmaps[name]
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
    elif name in namedPixmaps:
        return QtGui.QPixmap(':maestro/' + namedPixmaps[name])
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
