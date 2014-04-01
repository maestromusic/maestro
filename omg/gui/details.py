# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
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

import os

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt
translate = QtCore.QCoreApplication.translate

from . import mainwindow, dockwidget, selection, browser
from .. import logging, strutils, utils
from ..core import levels, tags, elements

logger = logging.getLogger(__name__)


class DetailsView(dockwidget.DockWidget):
    """A widget that lists all known information about a single element."""
    def __init__(self, parent=None, state=None, **args):
        super().__init__(parent, **args)        
        
        self.element = None
        self.tagsVisible = True
        self.contentsVisible = True
        self.stickersVisible = True
        self.history = []
        self.historyPosition = 0
        
        #widget = QtGui.QWidget()
        #layout = QtGui.QVBoxLayout(widget)
        #self.setWidget(widget)
        
        #buttonBar = QtGui.QHBoxLayout()
        #buttonBar.addStretch()
        #self.backButton = QtGui.QPushButton()
        #self.backButton.setFlat(True)
        #self.backButton.setIcon(self.style().standardIcon(QtGui.QStyle.SP_ArrowBack))
        #buttonBar.addWidget(self.backButton)
        #self.forwardButton = QtGui.QPushButton()
        #self.forwardButton.setIcon(self.style().standardIcon(QtGui.QStyle.SP_ArrowForward))
        #buttonBar.addWidget(self.forwardButton)
        #layout.addLayout(buttonBar)
        
        scrollArea = QtGui.QScrollArea()
        self.setWidget(scrollArea)
        scrollArea.setWidgetResizable(True)
        #layout.addWidget(scrollArea, 1)
        self.label = QtGui.QLabel()
        self.label.setTextFormat(Qt.RichText)
        self.label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.label.linkActivated.connect(self._handleLink)
        scrollArea.setWidget(self.label)
        selection.changed.connect(self._handleGlobalSelection)
        levels.real.connect(self._handleLevelChanged)
        levels.editor.connect(self._handleLevelChanged)
        
        # Load expand/collapse icons from style
        self.plusSign = QtGui.QPixmap(16, 12)
        self.plusSign.fill(Qt.transparent)
        option = QtGui.QStyleOption()
        option.type = QtGui.QStyleOption.SO_ViewItem
        option.rect = QtCore.QRect(QtCore.QPoint(0, 0), QtCore.QPoint(10, 10))
        option.state = QtGui.QStyle.State_Children
        painter = QtGui.QPainter(self.plusSign)
        self.style().drawPrimitive(QtGui.QStyle.PE_IndicatorBranch, option, painter)
        self.minusSign = QtGui.QPixmap(16, 12)
        self.minusSign.fill(Qt.transparent)
        option.state |= QtGui.QStyle.State_Open
        painter = QtGui.QPainter(self.minusSign)
        self.style().drawPrimitive(QtGui.QStyle.PE_IndicatorBranch, option, painter)
        
        self._handleGlobalSelection(selection.getGlobalSelection())
        
    def _handleGlobalSelection(self, selection):
        """Switch element when global selection changes."""
        if selection is not None:
            elements = list(selection.elements())
            if len(elements) == 1:
                self.setElement(elements[0])
                return
        self.setElement(None)
        
    def _handleLevelChanged(self, event):
        """React to the events from real or editor level."""
        #TODO: Depending on the level, the event might not actually affect self.element.
        # However, a change on real can affect the parents of an element on editor level.
        if self.element is not None and event.affects(self.element):
            self._update() 
            
    def setElement(self, element):
        """Set the element whose details are shown."""
        if element != self.element:
            self.element = element
            self._update()
        
    def _handleLink(self, href):
        """React to the user clicking links."""
        try:
            id = int(href)
            self.setElement(self.element.level.fetch(id))
        except ValueError:
            pass #TODO handle other hrefs
        if href == "tags":
            self.tagsVisible = not self.tagsVisible
            self._update()
        elif href == "contents":
            self.contentsVisible = not self.contentsVisible
            self._update()
        elif href == "stickers":
            self.stickersVisible = not self.stickersVisible
            self._update()
        elif href == "cover":
            dialog = CoverDialog(self.element, self)
            dialog.exec_()
        elif href.startswith('{'):
            if browser.defaultBrowser is not None:
                browser.defaultBrowser.search(href)
    
    def _update(self):
        """Update the HTML contents."""
        if self.element is None:
            self.label.setText('')
            return
        
        def link(href, text):
            return '<a href="{}" style="color: black; text-decoration: none">{}</a>'.format(href, text)
        def pixmap(pixmap, attributes=''):
            buffer = QtCore.QBuffer()
            pixmap.save(buffer, "PNG")
            string = bytes(buffer.buffer().toBase64()).decode('ascii')
            return '<img {} src="data:image/png;base64,{}" />'.format(attributes, string)
        
        el = self.element
        text = []
        text.append('<table>')
        
        # Cover and title
        text.append('<tr><td>')
        if el.hasCover():
            cover = el.getCover(60)
            if cover is not None:
                text.append(link("cover", pixmap(cover)))
        text.append('</td><td>')    
        text.append('<h2>{}</h2>'.format(Qt.escape(el.getTitle())))
        text.append('</td></tr>')
        
        # Type
        text.append('<tr><td>'+self.tr("Type: ")+'</td><td>')
        if el.isContainer():
            text.append(elements.getTypeTitle(el.type))
        else: text.append(Qt.escape(el.url.extension()))
        text.append('</td></tr>')
        
        # Url
        if el.isFile():
            text.append('<tr><td>'+self.tr("URL: ")+'</td><td>')
            text.append(str(el.url))
            text.append('</td></tr>')
        
        # Length, Size
        if el.isFile():
            text.append('<tr><td>'+self.tr("Size: ")+'</td><td>')
            value = strutils.formatLength(el.length)
            if el.url.scheme == 'file':
                try:
                    size = os.stat(el.url.absPath).st_size
                    value += ', '+strutils.formatSize(size)
                except Exception as e:
                    logger.debug(str(e))
                    pass
            text.append(value)
            text.append('</td></tr>')
            
        # Parents
        if len(el.parents) > 0:
            text.append('<tr><td>'+self.tr("Parents: ")+'</td><td>')
            parents = el.level.fetchMany(el.parents)
            text.append('<br />'.join(link(p.id, Qt.escape(p.getTitle())) for p in parents))
            text.append('</td></tr>')
            
        # Tags
        if len(el.tags) > 0:
            ln = link("tags", pixmap(self.minusSign if self.tagsVisible else self.plusSign))
            text.append('<tr><td>' + ln + self.tr("Tags: ") + '</td><td>')
            if self.tagsVisible:
                tagLines = []
                def addTag(tag, values):
                    links = []
                    for value in values:
                        if tag.type == tags.TYPE_TEXT:
                            value = value[:20]
                        elif tag.type == tags.TYPE_DATE:
                            value = str(value)
                        value = Qt.escape(value)
                        href = '{tag='+Qt.escape(tag.name)+'='+value+'}'
                        links.append(link(href, value))
                    tagLines.append("{}: {}".format(Qt.escape(tag.title), ', '.join(links)))
                for tag in tags.tagList:
                    if tag in el.tags: # First display the internal tags in their order
                        addTag(tag, el.tags[tag])
                    for tag, values in el.tags.items(): # Then add external tags
                        if not tag.isInDb():
                            addTag(tag, values)
                text.append('<br />'.join(tagLines))
            else:
                text.append(str(len(el.tags)))
            text.append('</td></tr>')
        
        # Flags
        if len(el.flags) > 0:
            text.append('<tr><td>'+self.tr("Flags: ")+'</td><td>')
            links = []
            for flag in el.flags:
                href = '{flag='+Qt.escape(flag.name)+'}'
                if flag.icon is not None:
                    icon = '<img src="{}" /> '.format(Qt.escape(flag.iconPath))
                else: icon = ''
                links.append(link(href, icon+Qt.escape(flag.name)))
            text.append(', '.join(links))
            text.append('</td></tr>')
            
        # Contents
        if el.isContainer():
            ln = link("contents", pixmap(self.minusSign if self.contentsVisible else self.plusSign))
            text.append('<tr><td>' + ln + self.tr("Contents: ") + '</td><td>')
            if self.contentsVisible:
                contents = el.level.fetchMany(el.contents)
                contents = ["{} - {}".format(pos, link(id, Qt.escape(c.getTitle())))
                            for (pos, id), c in zip(el.contents.items(), contents)]
                text.append('<br />'.join(contents))
            else: text.append(str(len(el.contents)))
            text.append('</td></tr>')
            
        if len(el.stickers) > 0:
            ln = link("stickers", pixmap(self.minusSign if self.stickersVisible else self.plusSign))
            text.append('<tr><td>' + ln + self.tr("Stickers: ") + '</td><td>')
            if self.stickersVisible:
                stickerLines = []
                for stickerType, values in el.stickers.items():
                    values = ', '.join(Qt.escape(v) for v in values)
                    stickerLines.append('{}: {}'.format(Qt.escape(stickerType), values))
                text.append('<br />'.join(stickerLines))
            else: text.append(str(sum(len(stickerList) for stickerList in el.stickers.values())))
            text.append('</td></tr>')
            
        text.append('</table>')
        self.label.setText(''.join(text))


mainwindow.addWidgetData(mainwindow.WidgetData(
                    id = "details",
                    name = translate("DetailsView", "Details"),
                    theClass = DetailsView,
                    icon = utils.getIcon('widgets/details.png'),
                    preferredDockArea = Qt.RightDockWidgetArea))


class CoverDialog(QtGui.QDialog):
    """Dialog that displays the cover of the given element."""
    def __init__(self, element, parent=None):
        super().__init__(parent)
        self.setWindowTitle(element.getTitle())
        pixmap = element.getCover()
        width = min(pixmap.width(), 800)
        height = min(pixmap.height(), 800)
        self.resize(width+2, height+2) # +2 suffices so that the scrollbar is not shown
        layout = QtGui.QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        label = QtGui.QLabel()
        label.setPixmap(pixmap)
        label.installEventFilter(self)
        scrollArea = QtGui.QScrollArea()
        scrollArea.setWidget(label)
        layout.addWidget(scrollArea)
    
    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.MouseButtonPress:
            self.close()
        return False
