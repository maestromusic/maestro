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

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from maestro import config

translate = QtCore.QCoreApplication.translate

"""This module contains the basic mechanism for action management. Every action that has a configurable
shortcut should be registered by the ActionManager instance created below. For actions on TreeViews, a special
mechanism is provided (see TreeActionConfiguration) that eases defining what actions should be available in a
certain tree view class, like the Browser or Editor.

Actions are grouped into *contexts*, which are used for grouping in the shortcut management GUI as well as in
context menus (by means of separators). For context names to be shown in translated version, add them to the
contextLabels dictionary.
"""

contextLabels = OrderedDict([
    ('misc',       translate('ActionContext', 'Misc')),
    ('view',       translate('ActionContext', 'View')),
    ('navigation', translate('ActionContext', 'Navigation')),
    ('elements',   translate('ActionContext', 'Elements')),
    ('browser',    translate('ActionContext', 'Browser')),
    ('playback',   translate('ActionContext', 'Playback')),
    ('plugins',    translate('ActionContext', 'Plugins'))])


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
        self.defaultShortcut = shortcut


class ActionManager(QtCore.QObject):
    """Manager class for actions. Keeps track of all Actions known to Maestro for which shortcuts are, or can
    be, defined.

    Each type of action has to be registered before it can be used (see registerAction), using a *unique*
    string identifier and a context, preferably one of those defined above in contextLabels. Shortcuts can be
    set and queried using shortcut() and setShortcut(); the latter emits the *shortcutChanged* signal.
    """
    shortcutChanged = QtCore.pyqtSignal(str, QtGui.QKeySequence)
    actionUnregistered = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.actions = {}
        """:type : dict[str, ActionDefinition]"""

    def contexts(self):
        return set(action.shortcut for action in self.actions.values())

    def shortcut(self, identifier: str) -> QtGui.QKeySequence:
        """Return the shortcut associated to the action with given *identifier*. Might return *None* if no
        shortcut is set.
        """
        if identifier in self.actions:
            return self.actions[identifier].shortcut
        return None

    def setShortcut(self, identifier, shortcut: QtGui.QKeySequence):
        """Set a shortcut for the action named `identifier`."""
        action = self.actions[identifier]
        action.shortcut = shortcut
        if action.shortcut == action.defaultShortcut:
            # remove from storage, if it's there (we only store non-defaults)
            if identifier in config.storage.gui.shortcuts:
                del config.storage.gui.shortcuts[identifier]
        else:
            config.storage.gui.shortcuts[identifier] = shortcut.toString()
        self.shortcutChanged.emit(identifier, shortcut)

    def registerAction(self, action: ActionDefinition):
        """Register a new action. Its identifier has to be unique."""
        if action.context not in contextLabels:
            raise ValueError('Action context "{}" not contained in context labels'.format(action.context))
        if action.identifier in self.actions:
            raise ValueError('Action identifier "{}" registered twice'.format(action.identifier))
        if action.identifier in config.storage.gui.shortcuts:
            action.shortcut = QtGui.QKeySequence(config.storage.gui.shortcuts[action.identifier],
                                                 QtGui.QKeySequence.PortableText)
        self.actions[action.identifier] = action

    def unregisterAction(self, identifier):
        """Unregister an action (e.g., when a plugin is disabled)."""
        del self.actions[identifier]
        self.actionUnregistered.emit(identifier)


manager = ActionManager()


class TreeActionDefinition(ActionDefinition):
    """Subclass for actions on TreeView instances. Augments ActionDefinition by information on how to
    instantiate the action for a given treeview instance.

    Args:
      actionCls: subclass of TreeAction
      **kwargs: additional keyword arguments passed to the action's constructor
    """

    def __init__(self, context, identifier, description, shortcut, actionCls, **kwargs):
        super().__init__(context, identifier, description, shortcut)
        self.actionCls = actionCls
        self.kwargs = kwargs

    def createAction(self, treeview):
        """Instantiate an action parented by *treeview*. The identifier specified by this definition is always
        passed to the action as keyword argument, in addition to self.kwargs.
        """
        return self.actionCls(treeview, identifier=self.identifier, **self.kwargs)


class Action(QtWidgets.QAction):
    """Base class for actions managed by Maestro.
    """

    label = None

    def __init__(self, parent, identifier, label=None):
        if label is None and self.label:
            label = self.label
        if label:
            super().__init__(label, parent)
        else:
            super().__init__(parent)
        if self.label:
            self.setText(self.label)
        self.identifier = identifier
        shortcut = manager.shortcut(identifier)
        if shortcut:
            self.setShortcut(shortcut)
        manager.shortcutChanged.connect(self._handleShortcutChange)

    def _handleShortcutChange(self, identifier, keySequence):
        if identifier == self.identifier:
            self.setShortcut(keySequence)


class GlobalAction(Action):

    identifier = None

    def __init__(self, parent, identifier=None, label=None):
        if identifier is None:
            identifier = type(self).identifier
        super().__init__(parent, identifier, label)
        self.triggered.connect(self.doAction)


    def doAction(self):
        raise NotImplementedError()

    @classmethod
    def register(cls, context='navigation', **kwargs):
        """Convenience method to register a new ActionDefinition to the ActionManager.
        """
        description = kwargs.get('description', cls.label)
        identifier = kwargs.get('identifier', cls.identifier)
        definition = ActionDefinition(context, identifier, description, kwargs.get('shortcut'))
        manager.registerAction(definition)


class TreeAction(Action):
    """Base class for actions on TreeView instances.

    TreeAction defines some common task on tree views and simplifies integration with the ActionManager. A
    TreeAction subclass can have a *label* class attribute, which is used as label (setText()) for the action.
    Otherwise, subclasses have to call setText() by themselves.

    Args:
      identifier: Identifier of the action. If an identifier is supplied and known by the ActionManager, the
        TreeAction will automatically set its shortcut and react to shortcutChanged events.
    """

    def __init__(self, parent, identifier):
        super().__init__(parent, identifier)
        self.setShortcutContext(Qt.WidgetShortcut)
        self.triggered.connect(self.doAction)

    def initialize(self, selection):
        """Called whenever the selection in the parent TreeView has changed. The action should analyze the
        selection in order to decide if it is enabled (valid for this selection) or not.
        """
        pass

    def doAction(self):
        """Performs the action This has to be implemented in all subclasses."""
        raise NotImplementedError()

    def level(self):
        """A shorthand function to determine the level of the treeview's model.
        :rtype: levels.Level"""
        return self.parent().model().level

    @classmethod
    def register(cls, identifier, context='elements', description=None, shortcut=None, **kwargs):
        """Convenience method to register a new TreeActionDefinition to the ActionManager.

        This method creates a new TreeActionDefinition object based on this class. The context defaults to
        'elements' but can be changed to anything else. *description* may be left blank if the class has a
        *label* class attribute, which is used for the action's description in that case.
        """
        if description is None:
            description = cls.label
        definition = TreeActionDefinition(context, identifier, description, shortcut, cls, **kwargs)
        manager.registerAction(definition)


class TreeActionConfiguration(QtCore.QObject):
    """Holds the configuration of actions associated to a certain TreeView subclass (Editor, Browser, ...).

    A TreeActionConfiguration consists of a nested structure of ActionTrees, each containing, divided into
    contexts, lists of actions (corresponding to one level of the context menu) and possibly child ActionTrees
    for sub-menus.

    Emits *actionDefinitionAdded* with the TreeActionDefinition as argument whenever such a definition was
    added to the configuration, and *actionDefinitonRemoved* with the action's identifier when it was removed.

    If an action is unregistered from the ActionManager, a TreeActionConfiguration will automatically remove
    that action from its configuration and emit actionDefinitionRemoved signals accordingly.
    """

    actionDefinitionAdded = QtCore.pyqtSignal(object)
    actionDefinitionRemoved = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.root = ActionTree(None, self)
        manager.actionUnregistered.connect(self.root.removeActionDefinition)

    def createMenu(self, parent):
        """Create and return a context menu for the given TreeView instance."""
        return self.root.createMenu(parent, parent.treeActions)

    def createActions(self, parent):
        """Instantiate all TreeActions defined by this configuration, with their parent set to *parent*. This
        method also alls parent.addAction() for every action created.

        Returns:
          A dictionary mapping identifier to TreeAction instance.
        """
        actions = {}
        for config in self.root.iterActions():
            identifier = config.identifier
            actions[identifier] = config.createAction(parent)
            parent.addAction(actions[identifier])
        return actions


class ActionTree(OrderedDict):
    """Defines one layer of the actions defined in a TreeActionConfiguration."""
    def __init__(self, name, parent):
        super().__init__()
        self.parent = parent
        # store the associated TreeActionConfiguration as self.config
        while isinstance(parent, ActionTree):
            parent = parent.parent
        self.config = parent
        self.name = name

    def addActionDefinition(self, action):
        """Add a new action definition on this layer. For convenience, *action* might be a definition string
        instead of a TreeActionDefinition; in that case, the definition is obtained from the ActionManager.
        """
        if isinstance(action, str):
            action = manager.actions[action]
        if action.context not in self:
            self[action.context] = OrderedDict()
        self[action.context][action.identifier] = action
        self.config.actionDefinitionAdded.emit(action)

    def addSubTree(self, name, context='misc'):
        """Add and return a new subtree named *name*."""
        if context not in self:
            self[context] = OrderedDict()
        tree = ActionTree(name, self)
        self[context][name] = tree
        return tree

    def removeActionDefinition(self, identifier):
        """Remove the action definition named *identifier* from this configuration. Recurses into sub-trees
        if necessary.
        """
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
        menu = QtWidgets.QMenu(parent)
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

