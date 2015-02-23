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

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
translate = QtCore.QCoreApplication.translate

from ... import application, database as db, utils, stack
from ...core import domains
from .. import dialogs, flexform


class DomainModel(flexform.FlexTableModel):
    """Data model for the domain manager."""
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.addField('name', self.tr("Name"), 'string')
        self.addField('number', self.tr("# of elements"), 'fixed')
        self.addField('number_files', self.tr("# of files"), 'fixed')
        self.addField('number_containers', self.tr("# of containers"), 'fixed')
        self.items = list(domains.domains)
        # Cache the element counts (we assume that they never change while this model is used)
        self.elementCounts = {domain: self._getCounts(domain) for domain in self.items}
        application.dispatcher.connect(self._handleDispatcher)
    
    def _getCounts(self, domain):
        """Return (as a tuple) the number of elements, files, containers in the given domain."""
        result = db.query("SELECT file,COUNT(*) FROM {p}elements WHERE domain=? GROUP BY file", domain.id)
        files = containers = 0
        for row in result:
            if row[0] == 0:
                containers = row[1]
            else: files += row[1]
        return (files+containers, files, containers)
    
    def _handleDispatcher(self, event):
        if isinstance(event, domains.DomainChangeEvent):
            if event.action == application.ChangeType.added:
                row = domains.domains.index(event.domain)
                self.insertItem(row, event.domain)
            elif event.action == application.ChangeType.deleted:
                self.removeItem(event.domain)
            else: self.itemChanged(event.domain)
    
    def getItemData(self, domain, field):
        if field.name == 'name':
            return domain.name
        else:
            fields = ['number', 'number_files', 'number_containers']
            return self.elementCounts[domain][fields.index(field.name)]

    def setItemData(self, domain, field, value):
        assert field.name == 'name'
        oldName = domain.name
        newName = value
        if oldName == newName:
            return False
        
        if not domains.isValidName(newName):
            dialogs.warning(self.tr("Cannot change domain"),
                            self.tr("'{}' is not a valid domain name.").format(newName))
            return False
        
        if domains.exists(newName):
            dialogs.warning(self.tr("Cannot change domain"),
                            self.tr("A domain named '{}' already exists.").format(newName))
            return False
              
        domains.changeDomain(domain, name=newName)
    
    
class DomainManager(flexform.FlexTable):
    """The DomainManager allows to add, edit and delete domains."""
    def __init__(self, dialog, panel):
        super().__init__(panel)
        self.setModel(DomainModel(self))
        self.addAction(NewDomainAction(self))
        self.addAction(stack.createUndoAction())
        self.addAction(stack.createRedoAction())
        self.addAction(DeleteDomainAction(self))
        
        
class NewDomainAction(QtWidgets.QAction):
    """Ask the user for a name and create a new domain."""
    def __init__(self, parent):
        super().__init__(utils.getIcon('add.png'), translate("NewDomainAction", "Create new domain..."),
                         parent)
        self.triggered.connect(self._triggered)
                   
    def _triggered(self):
        newDomain = createNewDomain(self.parent())
        if newDomain is not None:
            self.parent().selectItems([newDomain])


class DeleteDomainAction(QtWidgets.QAction):
    """Delete an empty domain."""
    def __init__(self, parent):
        super().__init__(utils.getIcon('delete.png'), translate("DeleteDomainAction", "Delete domain"),
                         parent)
        self.triggered.connect(self._triggered)
        parent.selectionChanged.connect(self._selectionChanged)
    
    def _selectionChanged(self):
        self.setEnabled(len(self.parent().selectedItems()) == 1)
        
    def _triggered(self):
        if len(self.parent().selectedItems()) == 1:
            if len(domains.domains) == 1:
                dialogs.warning(self.tr("Cannot delete domain"),
                                self.tr("Cannot delete the last domain."),
                                self.parent())
                return
            domain = self.parent().selectedItems()[0]
            number = self.parent().model._getCounts(domain)[0]
            if number > 0:
                dialogs.warning(self.tr("Cannot delete domain"),
                                self.tr("Cannot delete a domain that contains elements."),
                                self.parent())
                return
            domains.deleteDomain(domain)


def createNewDomain(parent=None):
    """Ask the user to supply a name and then create a new domain with this name. Return the new domain or
    None if no domain was created (e.g. if the user aborted the dialog or the supplied name was invalid)."""
    name, ok = QtWidgets.QInputDialog.getText(parent, translate("DomainManager", "New domain"),
                                    translate("DomainManager", "Please enter the name of the new domain:"))
    if not ok:
        return None
    
    if domains.exists(name):
        dialogs.warning(translate("DomainManager", "Cannot create domain"),
                        translate("DomainManager", "This domain does already exist."),
                        parent)
        return None
    elif not domains.isValidName(name):
        dialogs.warning(translate("DomainManager", "Invalid domain name"),
                        translate("DomainManager", "This is not a valid domain name."),
                        parent)
        return None
    
    return domains.addDomain(name)
    