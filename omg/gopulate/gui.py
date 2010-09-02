# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtCore, QtGui
from omg.gui.abstractdelegate import AbstractDelegate
from omg.gui.formatter import HTMLFormatter
import omg.gopulate
import omg.models
from omg import tags
from PyQt4.QtCore import Qt

class NewGopulateDelegate(QtGui.QStyledItemDelegate):
    """Draws Elements in the Gopulate view."""
    
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
        beforeTable = ''
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
                beforeTable = "<b>{:2}: </b>".format(elem.getPosition()) + beforeTable
            for k,vs in elem.tags.items():
                if k == tags.get("title") or k == tags.get("tracknumber"):
                    continue
                if k in elem.parent.sameTags:
                    continue
                tab.append( [str(k)] )
                for v in vs:
                    tab[-1].append(v)
        elif isinstance(elem, omg.models.Element):
            f = HTMLFormatter(elem)
            beforeTable = "<b>{:2}: </b>".format(elem.getPosition())
            beforeTable = beforeTable + f.detailView()
        # color codes
        if isinstance(elem, omg.gopulate.models.FileSystemFile) or isinstance(elem, omg.gopulate.models.GopulateContainer):
            if isinstance(elem, omg.gopulate.models.GopulateContainer) and elem.existingContainer:
                beforeTable = '<span style="background:pink">' + beforeTable + "</span>"
            else:
                beforeTable = '<span style="background:yellow">' + beforeTable + "</span>"
        elif isinstance(elem, omg.models.Element):
            beforeTable = '<span style="background:green">already in DB' + beforeTable + "</span>"
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


class GopulatTreeWidget(QtGui.QTreeView):
    """Suitable to display a GopulateTreeModel"""
    
    def __init__(self, parent = None):
        QtGui.QTreeView.__init__(self, parent)
        self.setItemDelegate(NewGopulateDelegate())
        self.setAlternatingRowColors(True)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)
        self.setSelectionMode(self.ExtendedSelection)
        
        self.mergeAction = QtGui.QAction("merge", self)
        self.mergeAction.triggered.connect(self._handleMerge)

    def contextMenuEvent(self, event):
        menu = QtGui.QMenu(self)
        menu.addAction(self.mergeAction)
        menu.popup(event.globalPos())
    
    def setModel(self, model):
        QtGui.QTreeView.setModel(self, model)
        model.modelReset.connect(self.expandAll)
        self.expandAll()
    
    def _handleMerge(self):
        title,flag = QtGui.QInputDialog.getText(self, "merge elements", "Name of new subcontainer:")
        if flag:
            self.model().merge(self.selectionModel().selectedIndexes(), title)
        
class GopulateWidget(QtGui.QWidget):
    """GopulateWidget consists of a GopulateTreeModel and buttons to control the populate process."""
    
    dbChanged = QtCore.pyqtSignal()
    
    def __init__(self, model):
        QtGui.QWidget.__init__(self)
        self.dirLabel = QtGui.QLabel()
        self.tree = GopulatTreeWidget()
        self.tree.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        model.modelReset.connect(self._updateLabel)
        
        self.accept = QtGui.QPushButton('accept')
        self.accept.pressed.connect(self._handleAcceptPressed)
        self.accept.released.connect(self._handleAcceptReleased)
        self.accept.clicked.connect(model.commit)
        
        self.next = QtGui.QPushButton('next')
        self.next.pressed.connect(self._handleNextPressed)
        self.next.released.connect(self._handleNextReleased)
        self.next.clicked.connect(model.nextDirectory)
        self.next.clicked.connect(self.dbChanged.emit)
        
        layout = QtGui.QVBoxLayout(self)
        layout.addWidget(self.dirLabel)
        layout.addWidget(self.tree)
        subLayout = QtGui.QHBoxLayout()
        subLayout.addWidget(self.accept)
        subLayout.addWidget(self.next)
        layout.addLayout(subLayout)
        
        self.tree.setModel(model)
        self.tree.setHeaderHidden(True)
        self._updateLabel()
        
    def _updateLabel(self):
        if self.tree.model().root:
            self.dirLabel.setText(self.tree.model().root.path)
    
    def _handleAcceptPressed(self):
        self.accept.setText("calculating audio hashes...")
    
    def _handleAcceptReleased(self):
        self.accept.setText("accept")
        
    def _handleNextPressed(self):
        self.next.setText("searching for new files...")
    
    def _handleNextReleased(self):
        self.next.setText("next")
