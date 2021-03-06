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

import os
from xml.sax import saxutils
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import Qt

from maestro import widgets, logging, utils
from maestro.core import levels, tags
from maestro.gui import selection
translate = QtCore.QCoreApplication.translate


def init():
    from maestro.widgets import WidgetClass
    WidgetClass(
        id='details', theClass=DetailsView, name=translate('DetailsView', 'Details'),
        icon=utils.images.icon('help-about'),
        preferredDockArea='right'
    ).register()


class DetailsView(widgets.Widget):
    """A widget that lists all known information about a single element."""
    def __init__(self, state=None, **args):
        super().__init__(**args)        
        
        self.element = None
        self.tagsVisible = True
        self.contentsVisible = True
        self.stickersVisible = True
        self.history = []
        self.historyPosition = 0
        
        #widget = QtWidgets.QWidget()
        #layout = QtWidgets.QVBoxLayout(widget)
        #self.setWidget(widget)
        
        #buttonBar = QtWidgets.QHBoxLayout()
        #buttonBar.addStretch()
        #self.backButton = QtWidgets.QPushButton()
        #self.backButton.setFlat(True)
        #self.backButton.setIcon(utils.images.icon("go-previous"))
        #buttonBar.addWidget(self.backButton)
        #self.forwardButton = QtWidgets.QPushButton()
        #self.forwardButton.setIcon(utils.images.standardIcon("go-next"))
        #buttonBar.addWidget(self.forwardButton)
        #layout.addLayout(buttonBar)
        
        scrollArea = QtWidgets.QScrollArea()
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scrollArea)
        scrollArea.setWidgetResizable(True)
        #layout.addWidget(scrollArea, 1)
        self.label = QtWidgets.QLabel()
        self.label.setTextFormat(Qt.RichText)
        self.label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.label.linkActivated.connect(self._handleLink)
        scrollArea.setWidget(self.label)
        selection.changed.connect(self._handleGlobalSelection)
        levels.real.connect(self._handleLevelChanged)
        levels.editor.connect(self._handleLevelChanged)
        
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
            browser = widgets.current('browser')
            if browser is not None:
                browser.search(href)
    
    def _update(self):
        """Update the HTML contents."""
        if self.element is None:
            self.label.setText('')
            return
        
        def link(href, text):
            return '<a href="{}" style="color: black; text-decoration: none">{}</a>'.format(href, text)
        
        expander = utils.images.pixmap("expander")
        collapser = utils.images.pixmap("collapser")
        
        el = self.element
        text = []
        text.append('<table>')
        
        # Cover and title
        text.append('<tr><td>')
        if el.hasCover():
            cover = el.getCover(60)
            if cover is not None:
                text.append(link("cover", utils.images.html(cover)))
        text.append('</td><td>')    
        text.append('<h2>{}</h2>'.format(saxutils.escape(el.getTitle())))
        text.append('</td></tr>')
        
        # Type
        text.append('<tr><td>'+self.tr("Type: ")+'</td><td>')
        if el.isContainer():
            text.append(el.type.title())
        else: text.append(saxutils.escape(el.url.extension))
        text.append('</td></tr>')
        
        # Domain
        text.append('<tr><td>'+self.tr("Domain: ")+'</td><td>')
        if el.domain is not None:
            text.append(saxutils.escape(el.domain.name))
        else: text.append(self.tr("None"))
        text.append('</td></tr>')
        
        # Url
        if el.isFile():
            text.append('<tr><td>'+self.tr("URL: ")+'</td><td>')
            text.append(str(el.url))
            text.append('</td></tr>')
        
        # Length, Size
        if el.isFile():
            text.append('<tr><td>'+self.tr("Size: ")+'</td><td>')
            value = utils.strings.formatLength(el.length)
            if el.url.scheme == 'file':
                try:
                    size = os.stat(el.url.path).st_size
                    value += ', '+utils.strings.formatSize(size)
                except Exception:
                    logging.info(__name__, "Could not read file size of '{}'.".format(el.url))
            text.append(value)
            text.append('</td></tr>')
            
        # Parents
        if len(el.parents) > 0:
            text.append('<tr><td>'+self.tr("Parents: ")+'</td><td>')
            parents = el.level.fetch(el.parents)
            text.append('<br />'.join(link(p.id, saxutils.escape(p.getTitle())) for p in parents))
            text.append('</td></tr>')
            
        # Tags
        if len(el.tags) > 0:
            ln = link("tags", utils.images.html(collapser if self.tagsVisible else expander))
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
                        value = saxutils.escape(value)
                        href = '{tag='+saxutils.escape(tag.name)+'='+value+'}'
                        links.append(link(href, value))
                    tagLines.append("{}: {}".format(saxutils.escape(tag.title), ', '.join(links)))
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
                href = '{flag='+saxutils.escape(flag.name)+'}'
                if flag.icon is not None:
                    icon = '<img src="{}" /> '.format(saxutils.escape(flag.iconPath))
                else: icon = ''
                links.append(link(href, icon+saxutils.escape(flag.name)))
            text.append(', '.join(links))
            text.append('</td></tr>')
            
        # Contents
        if el.isContainer():
            ln = link("contents", utils.images.html(collapser if self.contentsVisible else expander))
            text.append('<tr><td>' + ln + self.tr("Contents: ") + '</td><td>')
            if self.contentsVisible:
                contents = el.level.fetch(el.contents)
                contents = ["{} - {}".format(pos, link(id, saxutils.escape(c.getTitle())))
                            for (pos, id), c in zip(el.contents.items(), contents)]
                text.append('<br />'.join(contents))
            else: text.append(str(len(el.contents)))
            text.append('</td></tr>')
            
        if len(el.stickers) > 0:
            ln = link("stickers", utils.images.html(collapser if self.stickersVisible else expander))
            text.append('<tr><td>' + ln + self.tr("Stickers: ") + '</td><td>')
            if self.stickersVisible:
                stickerLines = []
                for stickerType, values in el.stickers.items():
                    values = ', '.join(saxutils.escape(v) for v in values)
                    stickerLines.append('{}: {}'.format(saxutils.escape(stickerType), values))
                text.append('<br />'.join(stickerLines))
            else: text.append(str(sum(len(stickerList) for stickerList in el.stickers.values())))
            text.append('</td></tr>')
        text.append('<tr><td>Level</td><td>{}</td></tr>'.format(el.level))
        text.append('</table>')
        self.label.setText(''.join(text))


class CoverDialog(QtWidgets.QDialog):
    """Dialog that displays the cover of the given element."""
    def __init__(self, element, parent=None):
        super().__init__(parent)
        self.setWindowTitle(element.getTitle())
        pixmap = element.getCover()
        width = min(pixmap.width(), 800)
        height = min(pixmap.height(), 800)
        self.resize(width+2, height+2) # +2 suffices so that the scrollbar is not shown
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        label = QtWidgets.QLabel()
        label.setPixmap(pixmap)
        label.installEventFilter(self)
        scrollArea = QtWidgets.QScrollArea()
        scrollArea.setWidget(label)
        layout.addWidget(scrollArea)
    
    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.MouseButtonPress:
            self.close()
        return False
