# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2013-2015 Martin Altmayer, Michael Helmling
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

from ..core import domains, elements
from .. import application
from maestro.filesystem import sources
from maestro import filesystem


class ContainerTypeBox(QtGui.QComboBox):
    """ComboBox to select a container type."""
    
    def __init__(self, currentType=None):
        """Create the ContainerTypeBox with *currentType* selected.
        
        If *currentType* is None, there will be a "None" entry which is then also the default.
        """
        # TODO: wollen wir das wirklich?
        super().__init__()
        if currentType is None:
            self.addItem('')
        for type in elements.ContainerType:
            if type == elements.ContainerType.Container:
                title = self.tr('(General) container')
            else:
                title = type.title()
            icon = type.icon()
            if icon is not None:
                self.addItem(icon, title, type)
            else:
                self.addItem(title, type)
            if type == currentType:
                self.setCurrentIndex(self.count() - 1)
                
    def currentType(self):
        """Return the currently selected container type."""
        return self.itemData(self.currentIndex())


class DomainBox(QtGui.QComboBox):
    """ComboBox to select a domain."""
    domainChanged = QtCore.pyqtSignal(domains.Domain)
    
    def __init__(self, currentDomain=None, parent=None):
        """Create the DomainBox with *currentDomain* selected."""
        super().__init__(parent)
        self.currentIndexChanged.connect(self._handleCurrentIndexChanged)
        self._fillBox(currentDomain)
        application.dispatcher.connect(self._handleDispatcher)
            
    def _fillBox(self, currentDomain):
        """Fill the box with all existing domains."""
        self.clear()
        for domain in sorted(domains.domains, key=lambda d: d.name):
            self.addItem(domain.name, domain)
            if domain == currentDomain:
                self.setCurrentIndex(self.count() - 1)
        if self.currentIndex() == -1:
            self.setCurrentIndex(0)
                
    def currentDomain(self):
        """Return the currently selected domain."""
        return self.itemData(self.currentIndex())
    
    def setCurrentDomain(self, domain):
        for i in range(self.count()):
            if domain == self.itemData(i):
                self.setCurrentIndex(i)
                return
        else: raise ValueError("Domain '{}' not contained in DomainBox.".format(domain.name))
    
    def _handleCurrentIndexChanged(self, i):
        self.domainChanged.emit(self.itemData(i))
        
    def _handleDispatcher(self, event):
        if isinstance(event, domains.DomainChangeEvent):
            currentDomain = self.currentDomain()
            self.currentIndexChanged.disconnect(self._handleCurrentIndexChanged)
            self._fillBox(currentDomain)
            self.currentIndexChanged.connect(self._handleCurrentIndexChanged)
            if self.currentDomain() != currentDomain:
                self.domainChanged.emit(self.currentDomain())
                

class SourceBox(QtGui.QComboBox):
    """ComboBox to select a filesystem source."""
    sourceChanged = QtCore.pyqtSignal(sources.Source)
    
    def __init__(self, currentSource=None):
        """Create the SourceBox with *currentSource* selected."""
        super().__init__()
        self._fillBox(currentSource)
        self.highlighted.connect(self._activated)
        self.currentIndexChanged.connect(self._handleCurrentIndexChanged)
        application.dispatcher.connect(self._handleDispatcher)
            
    def _fillBox(self, currentSource):
        """Fill the box with all existing domains."""
        self.clear()
        if len(filesystem._sources) > 0:
            for source in filesystem._sources:
                self.addItem(source.name, source)
                if source == currentSource:
                    self.setCurrentIndex(self.count() - 1)
        else:
            self.addItem("Create source...")
        if self.currentIndex() == -1:
            self.setCurrentIndex(0)
        
    def currentSource(self):
        """Return the currently selected source."""
        return self.itemData(self.currentIndex())
    
    def _handleCurrentIndexChanged(self, i):
        source = self.itemData(i)
        if source is not None:
            self.sourceChanged.emit(source)
        
    def _activated(self, i):
        if len(filesystem._sources) == 0 and i == 0:
            from . import preferences
            preferences.show("main/filesystem")
            
    def _handleDispatcher(self, event):
        if isinstance(event, filesystem.SourceChangeEvent):
            currentSource = self.currentSource()
            self.currentIndexChanged.disconnect(self._handleCurrentIndexChanged)
            self._fillBox(currentSource)
            self.currentIndexChanged.connect(self._handleCurrentIndexChanged)
            if self.currentSource() != currentSource and self.currentSource() is not None:
                self.sourceChanged.emit(self.currentSource())
