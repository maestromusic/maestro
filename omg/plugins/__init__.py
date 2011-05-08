# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
import os, sys

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

from omg import logging, config
from omg.gui import mainwindow

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger("omg.plugins")

# Directory containing the plugins
PLUGINDIR = "omg/plugins/"

if not os.path.isdir(PLUGINDIR):
    logger.error("Plugin directory does not exist.")
    plugins = []
else:
    # List of all plugins (or to be precise: all subdirectories of PLUGINDIR which contain a PLUGININFO file)
    plugins = [path for path in os.listdir(PLUGINDIR) if os.path.isdir(PLUGINDIR+path) 
                                                          and os.path.isfile(PLUGINDIR+path+"/PLUGININFO")]

# Dict mapping plugin-names to loaded modules. Contains all plugin-modules which have been loaded
loadedPlugins = {}

# List of all plugin-names that are currently enabled
enabledPlugins = []

def loadPlugins():
    """Import all plugins which should be loaded and enable them."""
    for pluginName in config.options.main.plugins:
        if pluginName != '':
            enablePlugin(pluginName)


def mainWindowInit():
    """Call plugin.mainWindowInit for all enabled plugins."""
    pluginAction = QtGui.QAction(mainwindow.mainWindow)
    pluginAction.setText(translate("PluginDialog","&Plugins..."))
    pluginAction.triggered.connect(_showPluginDialog)
    mainwindow.mainWindow.menus['extras'].addAction(pluginAction)
    
    for pluginName in enabledPlugins:
        plugin = loadedPlugins[pluginName]
        if hasattr(plugin,"mainWindowInit"):
            plugin.mainWindowInit()


def _showPluginDialog():
    from omg.plugins import dialog
    dialog.PluginDialog(mainwindow.mainWindow).exec_()


def enablePlugin(pluginName):
    """Enable the plugin with the given name. If it has not yet been imported, import it."""
    if pluginName in enabledPlugins:
        logger.warning("Tried to enable plugin '{}' that was already enabled.".format(pluginName))
    else:
        if pluginName not in loadedPlugins:
            logger.info("Loading plugin '{}'...".format(pluginName))
            loadedPlugins[pluginName] = getattr(__import__("omg.plugins",fromlist=[pluginName]),pluginName)
        else: logger.info("Enabling plugin '{}'...".format(pluginName))
        # Load default values for config and storage
        if hasattr(loadedPlugins[pluginName],'defaultConfig'):
            config.optionObject.loadPlugins(loadedPlugins[pluginName].defaultConfig())
        if hasattr(loadedPlugins[pluginName],'defaultStorage'):
            config.storageObject.loadPlugins(loadedPlugins[pluginName].defaultStorage())
        loadedPlugins[pluginName].enable()
        enabledPlugins.append(pluginName)
        if not pluginName in config.options.main.plugins:
            config.options.main.plugins = config.options.main.plugins + [pluginName]


def disablePlugin(pluginName):
    """Disable the plugin with the given name."""
    if pluginName not in enabledPlugins:
        logger.warning("Tried to disable plugin '{}' that was not enabled.".format(pluginName))
    else:
        logger.info("Disabling plugin '{}'...".format(pluginName))
        loadedPlugins[pluginName].disable()
        if hasattr(loadedPlugins[pluginName],'defaultConfig'):
            config.optionObject.removePlugins([pluginName])
        if hasattr(loadedPlugins[pluginName],'defaultStorage'):
            config.storageObject.removePlugins([pluginName])
        enabledPlugins.remove(pluginName)
        if pluginName in config.options.main.plugins:
            config.options.main.plugins = [name for name in config.options.main.plugins if name != pluginName]


def shutdown():
    """Shut down all plugins. This will invoke plugin.shutdown on all currently enabled plugins that implement the shutdown-method."""
    for name in enabledPlugins:
        if hasattr(loadedPlugins[name],'shutdown'):
            loadedPlugins[name].shutdown()
