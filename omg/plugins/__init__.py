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

logger = logging.getLogger("plugins")

# Directory containing the plugins
PLUGIN_DIR = "omg/plugins/"

if not os.path.isdir(PLUGIN_DIR):
    logger.error("Plugin directory does not exist.")
    plugins = []
else:
    # List of all plugins (or to be precise: all subdirectories of PLUGIN_DIR which contain a PLUGININFO file)
    plugins = [path for path in os.listdir(PLUGIN_DIR) if os.path.isdir(PLUGIN_DIR+path) 
                                                          and os.path.isfile(PLUGIN_DIR+path+"/PLUGININFO")]
                                                      
# Dict mapping plugin-names to loaded modules. Contains all plugin-modules which have been loaded
loadedPlugins = {}

# List of all plugin-names that are currently enabled
enabledPlugins = []

# Plugins that will be loaded on startup
#TODO: This should be editable from within the application
pluginsToLoad = ["coverfetcher"]

def loadPlugins():
    """Import all plugins which should be loaded and enable them."""
    for pluginName in pluginsToLoad:
        enablePlugin(pluginName)
        
def enablePlugin(pluginName):
    """Enable the plugin with the given name. If it has not yet been imported, import it."""
    assert pluginName not in enabledPlugins
    if pluginName not in loadedPlugins:
        logger.info("Loading plugin '{0}'...".format(pluginName))
        loadedPlugins[pluginName] = getattr(__import__("omg.plugins",fromlist=[pluginName]),pluginName)
    else: logger.info("Enabling plugin '{0}'...".format(pluginName))
    loadedPlugins[pluginName].enable()
    enabledPlugins.append(pluginName)

def disablePlugin(pluginName):
    """Disable the plugin with the given name."""
    assert pluginName in enabledPlugins
    loadedPlugins[pluginName].disable()
    enabledPlugins.remove(pluginName)
    
def teardown():
    """Tear down all plugins. This will invoke plugin.teardown on all currently enabled plugins that implement the teardown-method."""
    for name in enabledPlugins:
        if hasattr(loadedPlugins[name],'teardown'):
            loadedPlugins[name].teardown()