# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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

from .. import utils, config
from ..core import elements, levels, nodes, tags
from ..core.elements import ContainerType
from . import widgets


def question(title, text, parent=None):
    """Display a modal question dialog with the given *title* and *text*. Return True if the
    user selected "Yes" and False otherwise. The optional argument is the parent widget and default to the
    main window.
    :param str title: Window title
    :param str text: Main message
    :param QtGui.QWidget parent: (optional) parent window; defaults to Maestro's main window
    :returns: The user's answer
    :rtype: bool
    """
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


def getText(title, text, parent=None, default=''):
    result, ok = QtGui.QInputDialog.getText(parent, title, text, QtGui.QLineEdit.Normal, default)
    if ok:
        return result
    else: return None


class WaitingDialog(QtGui.QDialog):
    def __init__(self, title, text, cancelButton=True):
        from . import mainwindow
        super().__init__(mainwindow.mainWindow)
        self.setModal(True)
        self.setWindowTitle(title)
        layout = QtGui.QVBoxLayout()
        self.label = QtGui.QLabel(text)
        layout.addWidget(self.label)
        if cancelButton:
            btnBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Cancel)
            btnBox.rejected.connect(self.reject)
            layout.addWidget(btnBox)
        self.setLayout(layout)
    
    def setText(self, text):
        self.label.setText(text)


class FancyPopup(QtGui.QFrame):
    """Fancy popup that looks like a tooltip. It is shown beneath its parent component (usually the button
    that opens the popup).
    
    The popup will close itself if the user leaves its parent (the button that opened the popup)
    unless the popup is entered within a short timespan.
    """
    
    # Whether a timer is active that will close this widget (to prevent starting more than one timer)
    _timerActive = False
    
    def __init__(self, parent, width=300, height=170):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.Window | Qt.FramelessWindowHint)
        
        self.setMouseTracking(True)
        parent.installEventFilter(self)
        
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
        super().close()
    
    def showEvent(self,event):
        super().showEvent(event)
        self._moveToScreen()
    
    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self._tryClose(self.mapToGlobal(event.pos()))
    
    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Leave:
            self._tryClose(None)
        return False
    
    def _tryClose(self, pos):
        if self._timerActive:
            return
        if pos is None:
            underMouse = self.underMouse() or self.parent().underMouse()
        else:
            # for mouseMoveEvent of windows, underMouse() doesn't work here. On the last received
            # mouseMoveEvent when leaving the window, we are still "underMouse" (otherwise we shouldn't
            # get the event...) but the following test return false and correctly closes the window.
            widget = QtGui.QApplication.widgetAt(pos)
            if widget is None:
                underMouse = False
            else: underMouse = widget is self.parent() or self.isAncestorOf(widget)
            
        if not underMouse:
            QtCore.QTimer.singleShot(150, self._handleTimer)
            self._timerActive = True
            
    def _handleTimer(self):
        """Close the window shortly after the parent has been left by the cursor unless the cursor has
        entered the popup in the meantime."""
        self._timerActive = False
        if not self.underMouse():
            self.close()
            
            
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
        
        from . import dockwidget
        closeButton = dockwidget.DockWidgetTitleButton(
                                        QtGui.qApp.style().standardIcon(QtGui.QStyle.SP_TitleBarCloseButton))
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
      - a common prefix of the selected tag can be removed from the children,
      - numbers behind the prefix can be removed
      - the container can be assigned the common tags of all children
      - positions of subsequent elements can be lowered accordingly.
    """ 
    DefaultType = elements.ContainerType.Collection
    
    def __init__(self, model, wrappers, parent=None):
        """Set up the dialog for *wrappers* (all with the same parent) in *model*.
        
        *parent* refers to the Qt parent object.
        """
        super().__init__(parent)
        self.setMinimumSize(400, 250)
        self.setWindowTitle(self.tr("Merge elements"))
        self.model = model
        self.wrappers = wrappers
        self.elements = [wrapper.element for wrapper in wrappers]
        self.level = self.elements[0].level
        self.parentNode = wrappers[0].parent
        
        domain = self.wrappers[0].element.domain
        containerType = config.storage.gui.merge_dialog_container_type or self.DefaultType
        
        titleHint = ''
        prefix = ''
        if len(self.elements) > 1:
            allTitles = []
            for element in self.elements:
                if tags.TITLE in element.tags:
                    allTitles.extend(element.tags[tags.TITLE])
            # We require that the common title is separated from the rest by whitespace or punctuation
            # Otherwise elements that happen to start with the same letter would give a common prefix.
            prefix = utils.strings.commonPrefix(allTitles, separated=True)
            if len(prefix) > 0: 
                import string
                titleHint = prefix.strip(string.punctuation + string.whitespace)
        elif len(self.elements) == 1:
            titleHint = ' - '.join(self.elements[0].tags[tags.TITLE])
        
        layout = QtGui.QGridLayout()
        self.setLayout(layout)
        
        row = 0
        titleLineLayout = QtGui.QHBoxLayout()
        layout.addLayout(titleLineLayout, row, 0, 1, 2)
        titleLineLayout.addWidget(QtGui.QLabel(self.tr('Title of new container:')))
        self.titleEdit = QtGui.QLineEdit(titleHint)
        titleLineLayout.addWidget(self.titleEdit)
        
        row += 1
        label = QtGui.QLabel(self.tr('Domain:'))
        layout.addWidget(label, row, 0)
        self.domainBox = widgets.DomainBox(domain)
        layout.addWidget(self.domainBox, row, 1)
        
        row += 1
        label = QtGui.QLabel(self.tr('Container type:'))
        layout.addWidget(label, row, 0)
        self.parentTypeBox = widgets.ContainerTypeBox(containerType)
        layout.addWidget(self.parentTypeBox, row, 1)
        
        row += 1
        label = QtGui.QLabel(self.tr("Options"))
        label.setStyleSheet("QLabel { font-weight: bold }")
        label.setContentsMargins(0, 10, 0, 0)
        layout.addWidget(label, row, 0, 1, 2)
        
        row += 1
        self.commonTagsBox = QtGui.QCheckBox(self.tr("Assign common tags and flags"))
        self.commonTagsBox.setChecked(True)
        layout.addWidget(self.commonTagsBox, row, 0, 1, 2)
        
        if isinstance(self.parentNode, nodes.Wrapper):
            row += 1
            self.positionCheckBox = QtGui.QCheckBox(self.tr('Auto-adjust positions'))
            self.positionCheckBox.setChecked(True)
            layout.addWidget(self.positionCheckBox, row, 0, 1, 2)
        
        if any(element.isContainer() for element in self.elements):
            row += 1
            self.changeTypeBox = QtGui.QCheckBox(self.tr("Change content container types to:"))
            self.changeTypeBox.setChecked(False)
            layout.addWidget(self.changeTypeBox, row, 0)
            self.childrenTypeBox = widgets.ContainerTypeBox(ContainerType.Container)
            layout.addWidget(self.childrenTypeBox, row, 1)
            self.childrenTypeBox.setEnabled(False)
            self.changeTypeBox.toggled.connect(self.childrenTypeBox.setEnabled)
        
        if len(prefix) > 0:
            row += 1
            self.removePrefixBox = QtGui.QCheckBox(self.tr("Remove common title prefix:"))
            self.removePrefixBox.setChecked(True)
            layout.addWidget(self.removePrefixBox, row, 0)
            self.removeEdit = QtGui.QLineEdit(prefix)
            layout.addWidget(self.removeEdit, row, 1)
            self.removePrefixBox.toggled.connect(self.removeEdit.setEnabled)
        
        if len(self.elements) > 1 and any(utils.strings.numberFromPrefix(title[len(prefix):])[0] is not None 
                                          for title in allTitles):
            row += 1
            self.removeNumbersBox = QtGui.QCheckBox(self.tr("Remove numbers from title start"))
            self.removeNumbersBox.setChecked(True)
            layout.addWidget(self.removeNumbersBox, row, 0)
            
        row += 1
        layout.setRowStretch(row, 1)
        
        row += 1
        buttons = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Cancel | QtGui.QDialogButtonBox.Ok)
        buttons.accepted.connect(self.performMerge)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons, row, 0, 1, 2)
    
    def performMerge(self):
        """The actual merge operation."""
        self.level.stack.beginMacro(self.tr("Merge elements"), transaction=self.level is levels.real)
        containerTitle = self.titleEdit.text().strip()
        domain = self.domainBox.currentDomain()
        containerType = self.parentTypeBox.currentType()
        
        # Container tags & flags
        if self.commonTagsBox.isChecked():
            containerTags = tags.findCommonTags(self.elements)
            containerFlags = list(set.intersection(*(set(el.flags) for el in self.elements)))
        else:
            containerTags = tags.Storage()
            containerFlags = []
            
        if len(containerTitle) > 0:
            containerTags[tags.TITLE] = [containerTitle]
            if containerType == ContainerType.Album and tags.ALBUM not in containerTags:
                containerTags[tags.ALBUM] = [containerTitle]
                
        # Before creating anything, change tags of children (might raise filesystem errors)
        removePrefixes = hasattr(self, 'removePrefixBox') and self.removePrefixBox.isChecked()
        removeNumbers = hasattr(self, 'removeNumbersBox') and self.removeNumbersBox.isChecked()

        tagChanges = {}
        prefix = self.removeEdit.text() if removePrefixes else ''
        for element in self.elements:
            additions = removals = replacements = None
            if (removePrefixes or removeNumbers) and tags.TITLE in element.tags:
                removals, replacements = [], []
                for value in element.tags[tags.TITLE]:
                    if removePrefixes and value.startswith(prefix):
                        newValue = value[len(prefix):]
                    else: newValue = value
                    if removeNumbers:
                        number = utils.strings.numberFromPrefix(newValue)[1]
                        if len(number) > 0:
                            newValue = newValue[len(number):]
                    if len(newValue) == 0:
                        removals.append((tags.TITLE, value))
                    elif value != newValue:
                        replacements.append((tags.TITLE, value, newValue))
            if containerType == ContainerType.Album and tags.ALBUM not in element.tags:
                additions = [(tags.ALBUM, containerTitle)]
            tagChanges[element] = tags.TagDifference(additions=additions,
                                                     removals=removals,
                                                     replacements=replacements)

        if len(tagChanges) > 0:
            from ..filebackends import TagWriteError
            try:
                self.level.changeTags(tagChanges)
            except TagWriteError as e:
                e.displayMessage()
                self.level.stack.abortMacro()
                self.reject()
                return
                
        if hasattr(self, 'changeTypeBox') and self.changeTypeBox.isChecked():
            newType = self.childrenTypeBox.currentType()
            self.level.setTypes({elem: newType for elem in self.elements
                                               if elem.isContainer
                                               and elem.type != newType})
            
        contents = elements.ContentList.fromPairs(enumerate(self.elements, start=1))
        container = self.level.createContainer(domain = domain,
                                               tags = containerTags,
                                               flags = containerFlags,
                                               contents = contents,
                                               type = containerType)
                    
        if isinstance(self.parentNode, nodes.Wrapper):
            parent = self.parentNode.element
            insertPosition = self.wrappers[0].position
            insertIndex = parent.contents.positions.index(insertPosition)
            if self.positionCheckBox.isChecked():
                self.level.removeContentsAuto(parent, [wrapper.position for wrapper in self.wrappers])
                self.level.insertContentsAuto(parent, insertIndex, [container])
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
                
        self.level.stack.endMacro()
        
        if containerType != self.DefaultType:
            config.storage.gui.merge_dialog_container_type = containerType
        else: config.storage.gui.merge_dialog_container_type = None
            
        self.accept()
