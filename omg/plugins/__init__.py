# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
import os, sys, collections

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

from omg import logging, config, constants
from omg.gui import mainwindow

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)

# Directory containing the plugins
PLUGINDIR = os.path.join("omg", "plugins")
PLUGININFO_OPTIONS = collections.OrderedDict(
        ( ("name",None),  ("author",None) , ("version",None) , ("description", None), ("minomgversion","0.0.0"),
                      ("maxomgversion", "9999.0.0") ))

class Plugin(object):
    """A plugin that is available somewhere on the filesystem. May or may not be compatible with the current omg version,
    and may or may not be loaded."""
    
    def __init__(self, name):
        self.name = name
        self.enabled = False
        self.loaded = False
        self.module = None
        self.data = None
        self._readInfoFile(os.path.join(PLUGINDIR, name, 'PLUGININFO'))
        self.version_ok = constants.compareVersion(self.data['minomgversion']) >= 0 and constants.compareVersion(self.data['maxomgversion']) <= 0
    
    def load(self):
        if self.version_ok:
            """Imports the module, if it is compatible with the current OMG version. Otherwise an error is thrown."""
            self.module = getattr(__import__("omg.plugins",fromlist=[self.name]),self.name)
            self.loaded = True
        else:
            raise RuntimeError("Unsupported module version: {}".format(self.name))
    
    def enable(self):
        if not self.loaded:
            self.load()
        if not self.enabled:
            logger.info("Enabling plugin '{}'...".format(self.name))
            if hasattr(self.module,'defaultConfig'):
                config.optionObject.loadPlugins(self.module.defaultConfig())
            if hasattr(self.module,'defaultStorage'):
                config.storageObject.loadPlugins(self.module.defaultStorage())
            self.module.enable()
            self.enabled = True
            if not self.name in config.options.main.plugins:
                config.options.main.plugins = config.options.main.plugins + [self.name]

    def disable(self):
        """Disable the plugin with the given name."""
        if not self.enabled:
            logger.warning("Tried to disable plugin '{}' that was not enabled.".format(self.name))
        else:
            logger.info("Disabling plugin '{}'...".format(self.name))
            self.module.disable()
            if hasattr(self.module,'defaultConfig'):
                config.optionObject.removePlugins([self.name])
            if hasattr(self.module,'defaultStorage'):
                config.storageObject.removePlugins([self.name])
            if self.name in config.options.main.plugins:
                config.options.main.plugins = [n for n in config.options.main.plugins if n != self.name]
            self.enabled = False
        
    def shutdown(self):
        """Shut down the plugin if needed."""
        if hasattr(self.module, 'shutdown'):
            self.module.shutdown()
            
    def mainWindowInit(self):
        """Call initMainWindow of the plugin if that method exists."""
        if hasattr(self.module, 'mainWindowInit'):
            self.module.mainWindowInit()
            
    def _readInfoFile(self, path):
        """Reads the data contained in the PLUGININFO file."""
        with open(path,"r") as file:
            data = {}
            for line in file:
                key,value = line.split("=",1)
                key = key.strip().lower()
                value = value.strip()
                if key in PLUGININFO_OPTIONS:
                    data[key] = value
                else: logger.warning("Unknown key '{}' in {}".format(key,path))

            for (key,default) in PLUGININFO_OPTIONS.items():
                if key not in data:
                    if default is not None:
                        data[key] = default
                    else:
                        logger.warning("Missing key '{}' in {}".format(key,path))
                        data[key] = ""
            self.data = data
    def __str__(self):
        if self.data is not None:
            return self.data['name']
        else:
            return 'unknown plugin'
    def __repr__(self):
        return str(self)
plugins = {}
if not os.path.isdir(PLUGINDIR):
    logger.error("Plugin directory does not exist.")
else:
    # List of all plugins (or to be precise: all subdirectories of PLUGINDIR which contain a PLUGININFO file)
    plugins = {path:Plugin(path) for path in os.listdir(PLUGINDIR) if os.path.isdir(os.path.join(PLUGINDIR,path)) 
                                                          and os.path.isfile(os.path.join(PLUGINDIR,path,"PLUGININFO"))}
    plug_ordered = collections.OrderedDict()
    for pname in sorted(plugins.keys(), key = lambda k: plugins[k].data['name'].lower()):
        plug_ordered[pname] = plugins[pname]
    plugins = plug_ordered

# Dict mapping plugin-names to loaded modules. Contains all plugin-modules which have been loaded
loadedPlugins = {}

# List of all plugin-names that are currently enabled
enabledPlugins = []

def enablePlugins():
    """Import all plugins which should be loaded and enable them."""
    for pluginName in config.options.main.plugins:
        if pluginName != '':
            plugins[pluginName].enable()


def mainWindowInit():
    """Call plugin.mainWindowInit for all enabled plugins."""
    pluginAction = QtGui.QAction(mainwindow.mainWindow)
    pluginAction.setText(translate("PluginDialog","&Plugins..."))
    pluginAction.triggered.connect(_showPluginDialog)
    mainwindow.mainWindow.menus['extras'].addAction(pluginAction)
    
    for plugin in plugins.values():
        if plugin.enabled:
            plugin.mainWindowInit()


def _showPluginDialog():
    from omg.plugins import dialog
    dialog.PluginDialog(mainwindow.mainWindow).exec_()



def shutdown():
    """Shut down all plugins. This will invoke plugin.shutdown on all currently enabled plugins that implement the shutdown-method."""
    for plugin in plugins.values():
        plugin.shutdown()
