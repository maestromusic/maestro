#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
import sys
import os
import logging
import configparser
from PyQt4 import QtGui

logger = logging.getLogger("omg.plugins")

# Directory containing the plugins
PLUGIN_DIR = "omg/plugins/"

if not os.path.isdir(PLUGIN_DIR):
    logger.error("Plugin directory does not exist.")
    plugins = []
else:
    # List of all plugins (or to be precise: all subdirectories of PLUGIN_DIR which contain a PLUGININFO file)
    plugins = [path for path in os.listdir(PLUGIN_DIR) if os.path.isdir(os.path.join(PLUGIN_DIR,path)) 
                      and os.path.isfile(os.path.join(PLUGIN_DIR,path,"PLUGININFO"))]
                                                      
# Dict mapping plugin-names to loaded modules. Contains all plugin-modules which have been loaded
loadedPlugins = {}

# List of all plugin-names that are currently enabled
enabledPlugins = []

# Plugins that will be loaded on startup
#TODO: This should be editable from within the application
pluginsToLoad = ["coverfetcher", "dbinfo", "dbupdatedebugger", "wtx"]

def loadPlugins():
    """Import all plugins which should be loaded and enable them."""
    for pluginName in pluginsToLoad:
        enablePlugin(pluginName)
        
def enablePlugin(pluginName):
    """Enable the plugin with the given name. If it has not yet been imported, import it."""
    if pluginName in enabledPlugins:
        logger.warning("Tried to enable a plugin that was already enabled.")
    else:
        if pluginName not in loadedPlugins:
            logger.info("Loading plugin '{}'...".format(pluginName))
            loadedPlugins[pluginName] = getattr(__import__("omg.plugins",fromlist=[pluginName]),pluginName)
            loadedPlugins[pluginName].info = PluginInfo(pluginName)
        else: logger.info("Enabling plugin '{}'...".format(pluginName))
        loadedPlugins[pluginName].enable()
        enabledPlugins.append(pluginName)

def disablePlugin(pluginName):
    """Disable the plugin with the given name."""
    if pluginName not in enabledPlugins:
        logger.warning("Tried to disable a plugin that was not enabled.")
    else:
        logger.info("Disabling plugin '{}'...".format(pluginName))
        loadedPlugins[pluginName].disable()
        enabledPlugins.remove(pluginName)
    
def teardown():
    """Tear down all plugins. This will invoke plugin.teardown on all currently enabled plugins that implement the teardown-method."""
    for name in enabledPlugins:
        if hasattr(loadedPlugins[name],'teardown'):
            loadedPlugins[name].teardown()
class PluginInfo(object):
    def __init__(self, plugin):
        path = os.path.join(os.path.dirname(sys.modules["omg.plugins."+plugin].__file__), "PLUGININFO")
        with open(path, "rt") as plugininfo:
            for line in plugininfo:
                if "=" in line:
                    a,b = line.strip().split("=",1)
                    setattr(self, a, b)
def showListDialog(parent = None):
    """Display a dialog window listing available and enabled plugins."""
    dialog = QtGui.QDialog(parent)
    
    group = QtGui.QGroupBox()
    glayout = QtGui.QVBoxLayout()
    for plugin in loadedPlugins.values():
        glayout.addWidget(QtGui.QCheckBox("{0}: {1}".format(plugin.info.name, plugin.info.description)))
    group.setLayout(glayout)
    label = QtGui.QLabel(dialog.tr("Available plugins:"))
    layout = QtGui.QVBoxLayout()
    layout.addWidget(label)
    layout.addWidget(group)
    dialog.setLayout(layout)
    dialog.exec()