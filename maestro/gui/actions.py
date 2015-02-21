# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2015 Martin Altmayer, Michael Helmling
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

from collections import OrderedDict

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

translate = QtCore.QCoreApplication.translate


contextLabels = OrderedDict(navigation=translate('ActionContext', 'Navigation'),
                            elements=  translate('ActionContext', 'Elements'),
                            browser=   translate('ActionContext', 'Browser'),
                            playback=  translate('ActionContext', 'Playback'),
                            misc=      translate('ActionContext', 'Misc'),
                            plugins=   translate('ActionContext', 'Plugins'))


class ActionDefinition:
    """Data class defining a specific action, most notably its unique identifier and a potential shortcut.

    Args:
        context: The ActionContext; used for grouping in the shortcut configuration GUI
        identifier: unique identifier of the action
        description: translated description of the action
        shortcut: QKeySequence (or something that can be converted to one), or None
    """

    def __init__(self, context, identifier, description, shortcut=None):
        self.context = context
        self.identifier = identifier
        self.description = description
        if not isinstance(shortcut, QtGui.QKeySequence):
            shortcut = QtGui.QKeySequence(shortcut)
        self.shortcut = shortcut


class ActionManager(QtCore.QObject):
    """Manager class for actions. Keeps track of Actions for which shortcuts are (or can be) defined.
    """
    shortcutChanged = QtCore.pyqtSignal(str, QtGui.QKeySequence)
    actionUnregistered = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.actions = {}

    def shortcut(self, identifier) -> QtGui.QKeySequence:
        if identifier in self.actions:
            return self.actions[identifier].shortcut
        return None

    def setShortcut(self, identifier, shortcut: QtGui.QKeySequence):
        self.actions[identifier].shortcut = shortcut
        self.shortcutChanged.emit(identifier, shortcut)

    def registerAction(self, action):
        if action.identifier in self.actions:
            raise ValueError('Action identifier "{}" registered twice'.format(action.identifier))
        self.actions[action.identifier] = action

    def unregisterAction(self, identifier):
        del self.actions[identifier]
        self.actionUnregistered.emit(identifier)


manager = ActionManager()
setShortcut = manager.setShortcut
shortcut = manager.shortcut
registerAction = manager.registerAction


class TreeActionDefinition(ActionDefinition):
    """Subclass for actions on TreeView instances. Augments ActionDefinition by data how to instantiate the
    action for a given treeview.
    """

    def __init__(self, context, identifier, description, shortcut, actionCls, **kwargs):
        super().__init__(context, identifier, description, shortcut)
        self.actionCls = actionCls
        self.kwargs = kwargs

    def createAction(self, treeview):
        return self.actionCls(treeview, identifier=self.identifier, **self.kwargs)


class TreeAction(QtGui.QAction):
    """Base class for actions on TreeView instances.
    """
    label = None

    def __init__(self, parent, identifier=None, icon=None, tooltip=None):
        super().__init__(parent)
        self.identifier = identifier
        shortcut = manager.shortcut(identifier)
        if shortcut:
            self.setShortcut(shortcut)
            self.setShortcutContext(Qt.WidgetShortcut)
            manager.shortcutChanged.connect(self._handleShortcutChange)
        if self.label:
            self.setText(self.label)
        if icon:
            self.setIcon(icon)
        if tooltip:
            self.setToolTip((tooltip))
        self.triggered.connect(self.doAction)

    def _handleShortcutChange(self, identifier, keySequence):
        if identifier == self.identifier:
            self.setShortcut(keySequence)

    def initialize(self, selection):
        pass

    def doAction(self):
        raise NotImplementedError()

    def level(self):
        """A shorthand function to determine the level of the treeview's model.
        :rtype: levels.Level"""
        return self.parent().model().level

    @classmethod
    def register(cls, identifier, context='elements', description=None, shortcut=None, **kwargs):
        if description is None:
            if 'label' in kwargs:
                description = kwargs['label']
            else:
                description = cls.label
        definition = TreeActionDefinition(context, identifier, description, shortcut, cls, **kwargs)
        manager.registerAction(definition)


class ActionTree(OrderedDict):

    def __init__(self, name, parent):
        super().__init__()
        self.parent = parent
        while isinstance(parent, ActionTree):
            parent = parent.parent
        self.config = parent
        self['misc'] = OrderedDict()
        self.name = name

    def addActionDefinition(self, action):
        if isinstance(action, str):
            action = manager.actions[action]
        if action.context not in self:
            self[action.context] = OrderedDict()
        self[action.context][action.identifier] = action
        self.config.actionDefinitionAdded.emit(action)

    def addSubTree(self, name, context='misc'):
        if context not in self:
            self[context] = OrderedDict()
        tree = ActionTree(name, self)
        self[context][name] = tree
        return tree

    def removeActionDefinition(self, identifier):
        for section in self.values():
            if identifier in section:
                del section[identifier]
                self.config.actionDefinitionRemoved.emit(identifier)
                self.removeEmpty()
                return
            for subsect in section.values():
                if isinstance(subsect, ActionTree):
                    subsect.removeActionDefinition(identifier)

    def numEntries(self):
        return sum(len(section) for section in self.values())

    def removeEmpty(self):
        """Removes empty sections and subtrees."""
        emptyContexts = [context for context, section in self.items() if len(section) == 0]
        if len(emptyContexts):
            for context in emptyContexts:
                del self[context]
        if self.numEntries() == 0 and isinstance(self.parent, ActionTree):
            del self.parent[self.name]
            self.parent.removeEmpty()

    def createMenu(self, parent, actionDict):
        menu = QtGui.QMenu(parent)
        for context, section in self.items():
            if context != 'misc':
                sep = menu.addSeparator()
                if context in contextLabels:
                    sep.setText(contextLabels[context])
            for identifier, thing in section.items():
                if isinstance(thing, ActionTree):
                    subMenu = thing.createMenu(menu, actionDict)
                    subMenu.setTitle(identifier)
                    menu.addMenu(subMenu)
                else:
                    menu.addAction(actionDict[identifier])
        return menu

    def iterActions(self):
        for section in self.values():
            for item in section.values():
                if isinstance(item, ActionDefinition):
                    yield item
                else:
                    yield from item.iterActions()


class TreeActionConfiguration(QtCore.QObject):
    """Objects of this class define an action configuration for a treeview."""

    actionDefinitionAdded = QtCore.pyqtSignal(object)
    actionDefinitionRemoved = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.root = ActionTree(None, self)
        manager.actionUnregistered.connect(self.root.removeActionDefinition)

    def createMenu(self, parent, actionDict):
        return self.root.createMenu(parent, actionDict)

    def createActions(self, parent):
        actions = {}
        for config in self.root.iterActions():
            identifier = config.identifier
            actions[identifier] = config.createAction(parent)
            parent.addAction(actions[identifier])
        return actions