# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2013 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

from .. import database as db, utils
from ..core import elements, levels, nodes, tags
from . import tagwidgets


def question(title,text,parent=None):
    """Display a modal question dialog with the given *title* and *text*. Return True if the
    user selected "Yes" and False otherwise. The optional argument is the parent widget and default to the
    main window."""
    if parent is None:
        from . import mainwindow
        parent = mainwindow.mainWindow
    ans = QtGui.QMessageBox.question(parent,title,text,
                                     buttons = QtGui.QMessageBox.No | QtGui.QMessageBox.Yes)
    return ans == QtGui.QMessageBox.Yes


def warning(title,text,parent=None):
    """Display a modal warning dialog with the given *title* and *text*. The optional argument is the parent
    widget and default to the main window."""
    if parent is None:
        from . import mainwindow
        parent = mainwindow.mainWindow
    QtGui.QMessageBox.warning(parent, title, text)
    
    
class FancyPopup(QtGui.QFrame):
    """Fancy popup that looks like a tooltip. It is shown beneath its parent component (usually the button
    that opens the popup).
    
    The popup will close itself if the user leaves its parent (the button that opened the popup)
    unless the popup is entered within a short timespan.
    """
    
    # Whether a timer is active that will close this widget (to prevent starting more than one timer)
    _timerActive = False
    
    # A set of parents whose popup is open (static). Confer isActive
    _activeParents = set()
    
    def __init__(self, parent, width=300, height=170):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.Popup)
        FancyPopup._activeParents.add(parent)
        
        # Popup windows get mouse move events even if the pointer is outside the window
        self.setMouseTracking(True)
        
        # Fancy design code
        self.setAutoFillBackground(True)
        self.setFrameStyle(QtGui.QFrame.Box | QtGui.QFrame.Plain);
        self.setLineWidth(1);
        p = self.palette()
        p.setColor(QtGui.QPalette.Window,p.window().color().lighter(105))
        # Unbelievably this is used for the border...
        p.setColor(QtGui.QPalette.WindowText, Qt.darkGray)
        self.setPalette(p)
        
        effect = QtGui.QGraphicsDropShadowEffect()
        effect.setOffset(0,0)
        effect.setBlurRadius(20)
        self.setGraphicsEffect(effect)
        
        # Resize and move to the correct position
        self.resize(width,height)
        pos = self.parent().mapToGlobal(QtCore.QPoint(0,self.parent().height()))
        self.move(pos)
        self._moveToScreen()
        
    def _moveToScreen(self):
        # Unfortunately there seems to be no way to get the correct size prior to showing the dialog.
        # Therefore we correct offscreen positions after the dialog is shown as well as before (to try to
        # avoid flickering).
        pos = self.pos()
        if pos.x()+self.width() > QtGui.QApplication.desktop().width():
            pos.setX(QtGui.QApplication.desktop().width() - self.width())
        if pos.y()+self.height() > QtGui.QApplication.desktop().height():
            pos.setY(QtGui.QApplication.desktop().height() - self.height())
        self.move(pos)
        
    def close(self):
        self.parent().removeEventFilter(self)
        FancyPopup._activeParents.discard(self.parent())
        QtGui.QFrame.close(self)
    
    def showEvent(self,event):
        super().showEvent(event)
        self._moveToScreen()
    
    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        pos = self.mapToGlobal(event.pos())
        widget = QtGui.QApplication.widgetAt(pos)
        if widget is not None and widget is not self.parent() and not self.isAncestorOf(widget)\
                 and not self._timerActive:
            QtCore.QTimer.singleShot(150, self._handleTimer)
            self._timerActive = True
        
    def _handleTimer(self):
        """Close the window shortly after the parent has been left by the cursor unless the cursor has
        entered the popup in the meantime."""
        self._timerActive = False
        if not self.underMouse():
            self.close()
    
    @staticmethod
    def isActive(parent):
        """Return whether a fancy popup with *parent* as parent has been opened. Use this to avoid showing
        a second popup on the second click."""
        return parent in FancyPopup._activeParents
    
            
class FancyTabbedPopup(FancyPopup):
    """Fancy popup that contains a fancy TabWidget."""
    
    def __init__(self,parent,width=370,height=170):
        super().__init__(parent,width,height)
        # Create components
        self.setLayout(QtGui.QVBoxLayout())
        self.layout().setContentsMargins(0,0,0,0)
        self.tabWidget = QtGui.QTabWidget(self)
        self.tabWidget.setDocumentMode(True)
        self.layout().addWidget(self.tabWidget)
        
        closeButton = QtGui.QToolButton()
        closeButton.setIcon(utils.getIcon('close_button.png'))
        closeButton.setStyleSheet(
            "QToolButton { border: None; margin-bottom: 1px; } QToolButton:hover { border: 1px solid white; }")
        closeButton.clicked.connect(self.close)
        self.tabWidget.setCornerWidget(closeButton)
        
        # After changing the WindowText color for the FancyPopup's border we have to change the tabWidget's
        # palette so that the font is rendered normally.
        p = self.tabWidget.palette()
        p.setBrush(QtGui.QPalette.WindowText,self.parent().palette().windowText())
        self.tabWidget.setPalette(p)
        

class MergeDialog(QtGui.QDialog):
    """A dialog for merging several children of the same parent into a new subcontainer.
    
    Merging is a convenient way to add structural information to otherwise flat containers, e.g.
    pieces split up into several tracks.
    The procedure works as follows:
      1. the selected child elements are removed from the parent.
      2. a new container is created
      3. the selected elements are inserted into the new container
      4. the new container is inserted into the parent (at the position of the first child removed)
    The dialog allows to set a single tag for the new container (usually the title). Optionally,
      - a common prefix of the selected tag can be removed from the children
      - the container can be assigned the common tags of all children
      - positions of subsequent elements can be lowered accordinlgy.
    """ 
    
    def __init__(self, model, wrappers, parent=None):
        """Set up the dialog for *wrappers* (all with the same parent) in *model*.
        
        *parent* refers to the Qt parent object.
        """
        
        super().__init__(parent)
        self.setWindowTitle(self.tr("Merge elements"))
        self.model = model
        self.wrappers = wrappers
        self.elements = [wrapper.element for wrapper in wrappers]
        self.level = self.elements[0].level
        self.parentNode = wrappers[0].parent
        
        layout = QtGui.QGridLayout()
        self.tagChooser = tagwidgets.TagTypeBox(defaultTag=tags.TITLE, editable=False)
        self.tagChooser.tagChanged.connect(self.updateHints)
        layout.addWidget(self.tagChooser, 0, 0)
        label = QtGui.QLabel(self.tr('of new container:'))
        layout.addWidget(label, 0, 1)
        self.valueEdit = QtGui.QLineEdit()
        layout.addWidget(self.valueEdit, 0, 2)
        self.removePrefixBox = QtGui.QCheckBox()
        self.removePrefixBox.setChecked(True)
        layout.addWidget(self.removePrefixBox, 1, 0, 1, 2)
        self.removeEdit = QtGui.QLineEdit()
        layout.addWidget(self.removeEdit, 1, 2)
        self.removePrefixBox.toggled.connect(self.removeEdit.setEnabled)
        self.commonTagsBox = QtGui.QCheckBox(self.tr("Assign common tags and flags"))
        self.commonTagsBox.setChecked(True)
        layout.addWidget(self.commonTagsBox, 2, 0, 1, 3)
        if isinstance(self.parentNode, nodes.Wrapper):
            self.positionCheckBox = QtGui.QCheckBox(self.tr('Auto-adjust positions'))
            self.positionCheckBox.setChecked(True)
            layout.addWidget(self.positionCheckBox, 3, 0, 1, 3)
        buttons = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Cancel | QtGui.QDialogButtonBox.Ok)
        buttons.accepted.connect(self.performMerge)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons, layout.rowCount(), 0, 1, 3)
        self.updateHints(tags.TITLE)
        self.setLayout(layout)
        
    def updateHints(self, tag):
        """Update the hints for new tag value and remove prefix after a tag type is selected.
        
        The prefix hint is the longest common prefix of all children that have a tag of type *tag*.
        The value hint is the prefix with punctuation and whitespaces stripped.
        """
        from .. import strutils
        import string
        self.removePrefixBox.setText(self.tr("Remove prefixes from children's {}:").format(tag))
        noHint = all(tag not in element.tags for element in self.elements)
        self.removeEdit.setDisabled(noHint)
        if noHint:
            self.valueEdit.setText("")
            self.removeEdit.setText("")
        else:
            hintRemove = strutils.commonPrefix(str(element.tags[tag][0])
                            for element in self.elements if tag in element.tags)
            self.removeEdit.setText(hintRemove)
            hintValue = hintRemove.strip(string.punctuation + string.whitespace)
            self.valueEdit.setText(hintValue)
    
    def performMerge(self):
        """The actual merge operation.
        """
        self.level.stack.beginMacro(self.tr("merge"))
        if self.level is levels.real:
            db.transaction()
        if self.commonTagsBox.isChecked():
            containerTags = tags.findCommonTags(self.elements)
            containerFlags = list(set.intersection(*(set(el.flags) for el in self.elements)))
        else:
            containerTags = tags.Storage()
            containerFlags = []
        mergeTag = self.tagChooser.getTag()
        containerTags[mergeTag] = [ self.valueEdit.text() ]
        contents = elements.ContentList.fromPairs(enumerate(self.elements, start=1))
        container = self.level.createContainer(tags=containerTags, flags=containerFlags,
                                               contents=contents)
        if self.removePrefixBox.isChecked():
            childChanges = {}
            prefix = self.removeEdit.text()
            for elem in self.elements:
                if mergeTag not in elem.tags:
                    continue
                replacements = [(val, val[len(prefix):]) for val in elem.tags[mergeTag]
                                                         if val.startswith(prefix)
                                                         and val != prefix]
                removals = [val for val in elem.tags[mergeTag] if val == prefix]
                if len(replacements) > 0 or len(removals) > 0:
                    childChanges[elem] = tags.SingleTagDifference(mergeTag,
                                                                  removals=removals,
                                                                  replacements=replacements)
            if len(childChanges) > 0:
                from ..filebackends import TagWriteError
                try:
                    self.level.changeTags(childChanges)
                except TagWriteError as e:
                    e.displayMessage()
                    self.level.stack.abortMacro()
                    if self.level is levels.real:
                        db.commit()
                    self.reject()
                    return
        if isinstance(self.parentNode, nodes.Wrapper):
            parent = self.parentNode.element
            insertPosition = self.wrappers[0].position
            insertIndex = parent.contents.positions.index(insertPosition)
            if self.positionCheckBox.isChecked():
                self.level.removeContentsAuto(parent, [wrapper.position for wrapper in self.wrappers])
                self.level.insertContentsAuto(parent, insertIndex, [ container ])
            else:
                self.level.removeContents(parent, [wrapper.position for wrapper in self.wrappers])
                self.level.insertContents(parent, [(insertPosition, container)] )
        else:
            from ..models import leveltreemodel
            if isinstance(self.model, leveltreemodel.LevelTreeModel):
                rows = [self.parentNode.contents.index(wrapper) for wrapper in self.wrappers]
                insertIndex = rows[0]
                for i in range(len(rows)):
                    if rows[i] >= insertIndex:
                        rows[i] += 1
                # Insert first, otherwise EditorTreeModel might remove elements from the level.
                self.model.insertElements(self.parentNode, insertIndex, [container])
                self.model.removeElements(self.parentNode, rows)
            #else: Nothing to do: Merge has been performed in the level and the model does not allow a merge
                
        if self.level is levels.real:
            db.commit()
        self.level.stack.endMacro()
        self.accept()
        

class FlattenDialog(QtGui.QDialog):
    """A dialog for the "flatten" operation."""
    
    def __init__(self, hintRecursive = False, parent = None):
        super().__init__(parent)
        
        layout = QtGui.QVBoxLayout()
        layout.addWidget(QtGui.QLabel(self.tr("Flatten out containers"), self))
        self.recursiveBox = QtGui.QCheckBox(self.tr("recursively"))
        self.recursiveBox.setChecked(hintRecursive)
        layout.addWidget(self.recursiveBox)
        buttons = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Cancel | QtGui.QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setLayout(layout)
        
    def recursive(self):
        return self.recursiveBox.isChecked()
        