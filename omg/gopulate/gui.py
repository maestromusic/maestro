# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt
import os.path
import omg.models
from omg import tags, constants, config
from . import calculateMergeHint

def tagIcon(tag):
    path = os.path.join(constants.IMAGES, "icons", "tag_{}.png".format(tag.name))
    if os.path.exists(path):
            return path
    return None

class SuperNewDelegate(QtGui.QStyledItemDelegate):
    hMargin = 2
    vMargin = 1
    vItemSpace = 4
    hItemSpace = 4
    
    def __init__(self, parent = None):
        QtGui.QStyledItemDelegate.__init__(self,parent)
        self.iconSize = int(config.get("gui", "iconsize"))
        self.iconRect = QtCore.QRect(0, 0, self.iconSize, self.iconSize)
        self.font = QtGui.QFont()
    
    def formatTagValues(self, values):
        return ";;".join((str(x) for x in values))
    
    def paint(self,painter,option,index):
        if not isinstance(index.internalPointer(), omg.models.Element):
            return QtGui.QStyledItemDelegate.paint(self, painter, option, index)
        else:
            return self.layout(painter, option, index)
        
    def layout(self, painter, option, index):
        # Initialize

        
        if painter:
            painter.save()
            QtGui.QApplication.style().drawControl(QtGui.QStyle.CE_ItemViewItem,option,painter)
            option = QtGui.QStyleOptionViewItemV4(option)
            rect = QtCore.QRect(0,0,option.rect.width()-2*self.hMargin,option.rect.height()-2*self.vMargin)
            # Paint data
            painter.translate(option.rect.left()+self.hMargin,option.rect.top()+self.vMargin)
        else:
                width = 0
                height = 0
        elem = index.internalPointer()
        if elem.getPosition():
            self.font.setBold(True)
            positionSize = QtGui.QFontMetrics(self.font).size(Qt.TextSingleLine, str(elem.getPosition()))
            tagRenderStartX = positionSize.width() + 2*self.hItemSpace
            self.font.setBold(False)
        else: # no space for position needed if it is None
            tagRenderStartX = 0
        
        if painter:
            rect.setLeft(rect.left() + tagRenderStartX)
        if tags.TITLE in elem.tags:
            if elem.isContainer():
                self.font.setBold(True)
            self.font.setItalic(True)
            if painter:
                painter.setFont(self.font)
                boundingRect = painter.drawText(rect, Qt.TextSingleLine, self.formatTagValues(elem.tags[tags.TITLE]))
                rect.translate(0, boundingRect.height() + self.vItemSpace)
            else:
                fSize = QtGui.QFontMetrics(self.font).size(Qt.TextSingleLine, self.formatTagValues(elem.tags[tags.TITLE]))
                width = max(width, fSize.width())
                height += fSize.height() + self.hItemSpace
            
            self.font.setBold(False)
            self.font.setItalic(False)
            if painter:
                painter.setFont(self.font)
        for t,data in elem.tags.items():
            if data == [] or t.isIgnored() or t==tags.TITLE or (t==tags.ALBUM and elem.isAlbum()):
                continue
            if isinstance(elem.parent, omg.models.Element) and t in elem.parent.tags and data == elem.parent.tags[t]:
                continue
            

            iconPath = tagIcon(t)
            if iconPath:
                if painter:
                    img = QtGui.QImage(iconPath)
                    painter.drawImage(rect.topLeft(), img.scaled(self.iconRect.size()))
                    rect.setLeft(rect.left()+ self.iconSize + self.vItemSpace)
                else:
                    widthSoFar = self.iconSize + self.hItemSpace
            else:
                if painter:
                    boundingRect = painter.drawText(rect, Qt.TextSingleLine, "{}: ".format(t.name))
                    rect.setLeft(rect.left() + boundingRect.width() + self.hItemSpace)
                else:
                    fSize = QtGui.QFontMetrics(self.font).size(Qt.TextSingleLine, "{}: ".format(t.name))
                    widthSoFar = fSize.width() + self.hItemSpace
            if painter:
                painter.drawText(rect, Qt.TextSingleLine, self.formatTagValues(data))
                rect.translate(0, self.iconSize + self.vItemSpace)
                rect.setLeft(tagRenderStartX)
            else:
                fSize = QtGui.QFontMetrics(self.font).size(Qt.TextSingleLine, self.formatTagValues(data))
                width = max(width, fSize.width() + widthSoFar)
                height += self.iconSize + self.vItemSpace
        
        # paint the element position (~tracknumber) at the beginning of the line
        if painter:
            if elem.getPosition():
                self.font.setBold(True)
                painter.setFont(self.font)
                rect.setLeft(int((tagRenderStartX-positionSize.width())/2))
                rect.setTop(int((rect.height() -positionSize.height())/2))
                painter.drawText(rect, Qt.TextSingleLine, str(elem.getPosition()))
                self.font.setBold(False)
                painter.setFont(self.font)
            painter.restore()
        else:
            return QtCore.QSize(width + tagRenderStartX, height)
    
    def sizeHint(self, option, index):
        if not isinstance(index.internalPointer(), omg.models.Element):
            return QtGui.QStyledItemDelegate.sizeHint(self, option, index)
        else:
            size = self.layout(None, option, index)
            print(size)
            return size


class GopulatTreeWidget(QtGui.QTreeView):
    """Suitable to display a GopulateTreeModel"""
    
    def __init__(self, parent = None):
        QtGui.QTreeView.__init__(self, parent)
        self.setItemDelegate(SuperNewDelegate())
        self.setAlternatingRowColors(True)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)
        self.setSelectionMode(self.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.MoveAction)
        self.mergeAction = QtGui.QAction("merge", self)
        self.mergeAction.triggered.connect(self._handleMerge)

    def contextMenuEvent(self, event):
        if self.selectionModel().hasSelection():
            menu = QtGui.QMenu(self)
            menu.addAction(self.mergeAction)
            menu.popup(event.globalPos())
        print(self.size())
        
    
    def setModel(self, model):
        QtGui.QTreeView.setModel(self, model)
        model.modelReset.connect(self.expandAll)
        self.expandAll()
    
    def _handleMerge(self):
        indices = self.selectionModel().selectedIndexes()
        hint = calculateMergeHint(indices)
        title,flag = QtGui.QInputDialog.getText(self, "merge elements", "Name of new subcontainer:", text = hint)
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
