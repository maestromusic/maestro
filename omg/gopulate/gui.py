# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtCore, QtGui
from omg.gui.abstractdelegate import AbstractDelegate
import omg.gopulate
import omg.models
from omg import tags
from PyQt4.QtCore import Qt

class NewGopulateDelegate(QtGui.QStyledItemDelegate):
    def __init__(self, parent = None):
        QtGui.QAbstractItemDelegate.__init__(self, parent)
        self.doc = QtGui.QTextDocument()
      #  self.doc.setPageSize(QtCore.QSizeF(200,40))
      #  self.doc.setTextWidth(200)
        self.doc.setDefaultStyleSheet("td { padding-right: 5px }")
        
    def layout(self, index):
        elem = index.internalPointer()
        #self.doc.setHtml("<h2>spaaast</h2><img src=\"images/lastfm.gif\"></img>")
        #self.doc.adjustSize()
        tab = []
        beforeTable = ""
        if isinstance(elem,omg.gopulate.models.GopulateContainer):
            if tags.get("album") in elem.sameTags and tags.get("artist") in elem.sameTags:
                beforeTable += ", ".join(elem.tags['artist']) + " – " +  ", ".join(elem.tags['album'])
                if "date" in elem.sameTags:
                    beforeTable += " ({})".format(", ".join(elem.tags['date']))
            for k in elem.sameTags:
                if k == tags.get("album") or k == tags.get("artist") or k == tags.get("date"):
                    continue
                tab.append( [str(k)])
                for v in elem.tags[k]:
                    tab[-1].append(v)
        elif isinstance(elem,omg.gopulate.models.FileSystemFile):
            if tags.get("title") in elem.tags:
                beforeTable = ", ".join(elem.tags['title'])
                if "tracknumber" in elem.tags:
                    beforeTable = "<b>{:2}: </b>".format(", ".join(elem.tags['tracknumber'])) + beforeTable
            for k,vs in elem.tags.items():
                if k == tags.get("title") or k == tags.get("tracknumber"):
                    continue
                if k in elem.parent.sameTags:
                    continue
                tab.append( [str(k)] )
                for v in vs:
                    tab[-1].append(v)
        elif isinstance(elem, omg.models.Element):
            if elem.isContainer():
                beforeTable = "container:"
            else:
                beforeTable = "file:"
        # color codes
        if isinstance(elem, omg.gopulate.models.FileSystemFile) or isinstance(elem, omg.gopulate.models.GopulateContainer):
            beforeTable = '<span style="background:yellow">' + beforeTable + "</span>"
        elif isinstance(elem, omg.models.Element):
            beforeTable = '<span style="background:green">' + beforeTable + "</span>"
        lines = beforeTable
        if len(tab) > 0:
            cols = max(len(x) for x in tab)
            lines += '<table><tr>'
            lines += "</tr><tr>".join(self._layoutRow(row, cols) for row in tab)
            lines += "</tr>"
            lines += "</table>"
        self.doc.setHtml(lines)
        
    def _layoutRow(self, row, cols):
        lines = ""
        if len(row) > 1:
            lines += "<td><i>{}</i></td>".format(row[0])
            for elem in row[1:-1]:
                    lines += '<td align="left">{}</td>'.format(elem)
        if len(row) < cols:
            lines += '<td align="left" colspan="{}">{}</td>'.format(1 + cols - len(row), row[-1])
        else:
            lines += "<td>{}</td>".format(row[-1])
        return lines
        
    def paint(self, painter, option, index):
        self.layout(index)
        option = QtGui.QStyleOptionViewItemV4(option)
        QtGui.QApplication.style().drawControl(QtGui.QStyle.CE_ItemViewItem,option,painter)
        painter.save()
        painter.translate(option.rect.x(), option.rect.y())
        self.doc.drawContents(painter) #, QtCore.QRectF(option.rect))
        painter.restore()
    
    def sizeHint(self, option, index):
        self.layout(index)
        return self.doc.size().toSize()

class GopulateDelegate(AbstractDelegate):
    def __init__(self,parent = None):
        AbstractDelegate.__init__(self,parent)
        
    def layout(self, index):
        elem = index.internalPointer()
        if (isinstance(elem,omg.gopulate.models.GopulateContainer)):
            if "album" in elem.sameTags and "artist" in elem.sameTags:
                titleLine = '"{}" from {}'.format(", ".join(elem.tags['album']), ", ".join(elem.tags['artist']))
                if "date" in elem.sameTags:
                    titleLine += " ({})".format(", ".join(elem.tags['date']))
                self.addLine(titleLine)
            for k in elem.sameTags:
                if k == tags.get("album") or k == tags.get("artist") or k == tags.get("date"):
                    continue
                for v in elem.tags[k]:
                    self.addLine("{}={}".format(k,v))
        elif (isinstance(elem,omg.gopulate.models.FileSystemFile)):
            if tags.get("title") in elem.tags:
                firstLine = ", ".join(elem.tags['title'])
                if "tracknumber" in elem.tags:
                    firstLine = "{:2} - ".format(", ".join(elem.tags['tracknumber'])) + firstLine
                self.addLine(firstLine)
            for k,vs in elem.tags.items():
                if k == tags.get("title") or k == tags.get("tracknumber"):
                    continue
                if k in elem.parent.sameTags:
                    continue
                for v in vs:
                    self.addLine("{}={}".format(k,v))
        
class GopulateEditorWidget(QtGui.QLabel):
    def __init__(self, parent = None):
        QtGui.QWidget.__init__(self,parent)
        self.setText('<p> omgwtf? </p><br /><p><b>OMGWTF!?</b></p>')
        
    def setElement(self, cur, prev):
        self.element = cur.internalPointer()
        self.setText("\n".join("{}={}".format(k,v) for k,v in self.element.tags.items()))

class GopulatTreeWidget(QtGui.QTreeView):
    
    def __init__(self, parent = None):
        QtGui.QTreeView.__init__(self, parent)
        self.setItemDelegate(NewGopulateDelegate())
        self.setAlternatingRowColors(True)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)
        self.setSelectionMode(self.ExtendedSelection)

    def contextMenuEvent(self, event):
        print("context!")
        ac = QtGui.QAction("test",self)
        menu = QtGui.QMenu(self)
        menu.addAction(ac)
        menu.popup(event.globalPos())
        
class GopulateWidget(QtGui.QWidget):
    
    def __init__(self, model=None):
        QtGui.QWidget.__init__(self)
        self.tree = GopulatTreeWidget()
        self.editor = GopulateEditorWidget()
        self.tree.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.accept = QtGui.QPushButton('accept')
        layout = QtGui.QVBoxLayout(self)
        midLayout = QtGui.QHBoxLayout()
        midLayout.addWidget(self.tree)
    #    midLayout.addWidget(self.editor)
        layout.addLayout(midLayout)
        layout.addWidget(self.accept)
        
        self.tree.setModel(model)
        self.tree.setHeaderHidden(True)
