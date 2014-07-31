# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt
translate = QtCore.QCoreApplication.translate

from ... import application, database as db, utils, stack, constants
from ...core import flags
from .. import dialogs, flexform


class FlagModel(flexform.FlexTableModel):
    """Data model for the FlagManager."""
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.addField('icon', self.tr("Icon"), 'image', folders=[':omg/flags', ':omg/tags'])
        self.addField('name', self.tr("Name"), 'string')
        self.addField('number', self.tr("# of elements"), 'fixed')
        self.items = list(flags.allFlags())
        # Cache the element counts (we assume that they never change while this model is used)
        self.elementCounts = dict(db.query("SELECT flag_id, COUNT(*) FROM {p}flags GROUP BY flag_id"))
        application.dispatcher.connect(self._handleDispatcher)
        
    def _handleDispatcher(self, event):
        if isinstance(event, flags.FlagTypeChangeEvent):
            if event.action == constants.ADDED:
                row = flags.allFlags().index(event.flagType)
                self.insertItem(row, event.flagType)
            elif event.action == constants.DELETED:
                self.removeItem(event.flagType)
            else: self.itemChanged(event.flagType)
                
    def getItemData(self, flag, field):
        if field.name == 'icon':
            if flag.iconPath is not None:
                return flag.iconPath
            else: return None
        elif field.name == 'name':
            return flag.name
        else: return self.elementCounts.get(flag.id, 0)

    def setItemData(self, flag, field, value):
        if field.name == 'name':
            oldName = flag.name
            newName = value
            if oldName == newName:
                return False
        
            if not flags.isValidFlagname(newName):
                dialogs.warning(self.tr("Cannot change flag"),
                                self.tr("'{}' is not a valid flagname.").format(newName))
                return False
        
            if flags.exists(newName):
                dialogs.warning(self.tr("Cannot change flag"),
                                self.tr("A flag named '{}' does already exist.").format(newName))
                return False
            
            flags.changeFlagType(flag, name=newName)
            return True
        elif field.name == 'icon':
            flags.changeFlagType(flag, iconPath=value)
            return True
        else: assert False
    
    def getElementCount(self, flag):
        """Return the number of elements having the given flag."""
        return db.query("SELECT COUNT(*) FROM {p}flags WHERE flag_id = ?", flag.id).getSingle()


class FlagManager(flexform.FlexTable):
    """The FlagManager allows to add, edit and delete flagtypes."""
    def __init__(self, dialog, panel):
        super().__init__(panel)
        self.setModel(FlagModel(self))
        self.addAction(NewFlagAction(self))
        self.addAction(stack.createUndoAction())
        self.addAction(stack.createRedoAction())
        self.addAction(DeleteFlagAction(self))
        self.addAction(ShowInBrowserAction(self))


class NewFlagAction(QtGui.QAction):
    """Ask the user for a name and add a new flag to the database."""
    def __init__(self, parent):
        super().__init__(utils.getIcon('add.png'), translate("NewFlagAction", "Create new flag..."), parent)
        self.triggered.connect(self._triggered)
        
    def _triggered(self):
        newFlag = createNewFlagType(self.parent())
        if newFlag is not None:
            self.parent().selectItems([newFlag])


class DeleteFlagAction(QtGui.QAction):
    """Confirm and delete a flag from the database."""
    def __init__(self, parent):
        super().__init__(utils.getIcon('delete.png'), translate("DeleteFlagAction", "Delete flag"), parent)
        self.triggered.connect(self._triggered)
        parent.selectionChanged.connect(self._selectionChanged)
    
    def _selectionChanged(self):
        self.setEnabled(len(self.parent().selectedItems()) == 1)
        
    def _triggered(self):
        if len(self.parent().selectedItems()) == 1:
            flag = self.parent().selectedItems()[0]
            number = self.parent().model.getElementCount(flag)
            if number > 0:
                question = self.tr("Do you really want to delete the flag '{}'? "
                                   "It will be deleted from %n element(s).", None, number).format(flag.name)
                if not dialogs.question(self.tr("Delete flag?"), question, self.parent()):
                    return
            flags.deleteFlagType(flag)


class ShowInBrowserAction(QtGui.QAction):
    """Load all elements containing the selected flag into the default browser."""
    def __init__(self, parent):
        super().__init__(utils.getIcon('preferences/goto.png'),
                         translate("ShowInBrowserAction", "Show in browser"),
                         parent)
        parent.selectionChanged.connect(self._selectionChanged)
        self.triggered.connect(self._triggered)
        self._selectionChanged()
    
    def _selectionChanged(self):
        from .. import browser
        self.setEnabled(len(self.parent().selectedItems()) == 1 and browser.defaultBrowser is not None)
    
    def _triggered(self):
        from .. import browser
        if len(self.parent().selectedItems()) == 1 and browser.defaultBrowser is not None:
            flag = self.parent().selectedItems()[0]
            browser.defaultBrowser.search('{flag='+flag.name+'}') 
    
    
def createNewFlagType(parent=None):
    """Ask the user to supply a name and then create a new flag with this name. Return the new flag or None
    if no flag was created (e.g. if the user aborted the dialog or the supplied name was invalid).
    """
    name = dialogs.getText(translate("FlagManager", "New Flag"),
                           translate("FlagManager", "Please enter the name of the new flag:"),
                           parent)
    if name is None:
        return None
    
    if flags.exists(name):
        dialogs.warning(translate("FlagManager", "Cannot create flag"),
                        translate("FlagManager", "This flag does already exist."),
                        parent)
        return None
    elif not flags.isValidFlagname(name):
        dialogs.warning(translate("FlagManager", "Invalid flagname"),
                        translate("FlagManager", "This is not a valid flagname."),
                        parent)
        return None
    
    return flags.addFlagType(name)
    