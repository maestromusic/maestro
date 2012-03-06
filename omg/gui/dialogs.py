# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
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
from .. import utils


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
    """
    # The popup will close itself if the user leaves its parent (the button that opened the popup)
    # unless the popup is entered within a short timespan.
    _entered = False
    
    # A set of parents whose popup is open (static). Confer isActive
    _activeParents = set()
    
    # While fixPopup is True, the popup will not close when the mouse leaves.
    fixPopup = False
    
    def __init__(self,parent = None):
        QtGui.QFrame.__init__(self,parent)
        self.setWindowFlags(self.windowFlags() | Qt.Popup)
        parent.installEventFilter(self)
        FancyPopup._activeParents.add(parent)
        
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
        
        # Move to correct position
        pos = self.parent().mapToGlobal(QtCore.QPoint(0,self.parent().height()))
        #TODO: It would be nice to ensure that the window does not leave the screen.
        # Unfortunately there seems to be no way to get the correct size prior to showing the dialog.
        self.move(pos)
        
        # This is just a reasonable default value. Resize it in subclasses as you like
        self.resize(300,170)
        
    def close(self):
        self.parent().removeEventFilter(self)
        FancyPopup._activeParents.discard(self.parent())
        QtGui.QFrame.close(self)
    
    def enterEvent(self,event):
        self._entered = True
        QtGui.QFrame.enterEvent(self,event)
    
    def leaveEvent(self,event):
        if self.isVisible() and not self.fixPopup:
            self.close()
             
    def eventFilter(self,object,event):
        if event.type() == QtCore.QEvent.Leave:
            QtCore.QTimer.singleShot(100,self._handleTimer)
        return False
        
    def _handleTimer(self):
        """Close the window shortly after the parent has been left by the cursor unless the cursor has
        entered the popup in the meantime."""
        if not self._entered:
            self.close()
    
    @staticmethod
    def isActive(parent):
        """Return whether a fancy popup with *parent* as parent has been opened. Use this to avoid showing
        a second popup on the second click."""
        return parent in FancyPopup._activeParents
    
            
class FancyTabbedPopup(FancyPopup):
    """Fancy popup that contains a fancy TabWidget."""
    
    # The popup will close itself if the user leaves its parent (the button that opened the popup)
    # unless the popup is entered within a short timespan.
    _entered = False
    
    def __init__(self,parent = None):
        super().__init__(parent)
        # Create components
        self.setLayout(QtGui.QVBoxLayout())
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
    """This dialog is shown if the user requests to merge some children into a new
    intermediate container."""
    
    def __init__(self, hintTitle, hintRemove, askForPositionAdjusting, parent = None):
        super().__init__(parent)
        layout = QtGui.QGridLayout()
        label = QtGui.QLabel(self.tr('Title of new container:'))
        layout.addWidget(label, 0, 0)
        self.titleEdit = QtGui.QLineEdit(hintTitle)
        layout.addWidget(self.titleEdit, 0, 1)
        self.checkBox = QtGui.QCheckBox(self.tr('Remove from titles:'))
        self.checkBox.setChecked(True)
        layout.addWidget(self.checkBox, 1, 0)
        self.removeEdit = QtGui.QLineEdit(hintRemove)
        layout.addWidget(self.removeEdit, 1, 1)
        self.checkBox.toggled.connect(self.removeEdit.setEnabled)
        
        if askForPositionAdjusting:
            self.positionCheckBox = QtGui.QCheckBox(self.tr('Auto-adjust positions'))
            self.positionCheckBox.setChecked(True)
            layout.addWidget(self.positionCheckBox, 2, 0, 1, 2)
        hLayout = QtGui.QHBoxLayout()
        self.cancelButton = QtGui.QPushButton(self.tr('Cancel'))
        self.okButton = QtGui.QPushButton(self.tr('OK'))
        self.cancelButton.clicked.connect(self.reject)
        self.okButton.clicked.connect(self.accept)
        self.okButton.setDefault(True)
        hLayout.addStretch()
        hLayout.addWidget(self.cancelButton)
        hLayout.addWidget(self.okButton)
        layout.addLayout(hLayout, 3 if askForPositionAdjusting else 2, 0, 1, 2)
        layout.setColumnStretch(1, 1)
        self.setLayout(layout)
        
    def newTitle(self):
        return self.titleEdit.text()
    
    def removeString(self):
        return self.removeEdit.text() if self.checkBox.isChecked() else ''
    
    def adjustPositions(self):
        if hasattr(self, 'positionCheckBox'):
            return self.positionCheckBox.isChecked()
        else:
            return False

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
        