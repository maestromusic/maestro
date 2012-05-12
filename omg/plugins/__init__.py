# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
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

import collections, importlib

from PyQt4 import QtCore

from .. import logging, config, constants

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)


class Plugin(object):
    """A plugin that is available somewhere on the filesystem. May or may not be compatible with the
    current omg version, and may or may not be loaded."""
    
    def __init__(self, name):
        self.name = name
        self.enabled = False
        self.loaded = False 
        self.package = importlib.import_module('.'+self.name,'omg.plugins')
        
        self.versionOk = True
        if (hasattr(self.package,'MINOMGVERSION')):
            if constants.compareVersion(self.package.MINOMGVERSION) < 0:
                self.versionOk = False
        if (hasattr(self.package,'MAXOMGVERSION')):
            if constants.compareVersion(self.package.MAXOMGVERSION) > 0:
                self.versionOk = False
    
    def load(self):
        """Imports the module, if it is compatible with the current OMG version.Otherwise an error is thrown.
        """
        if self.versionOk:
            self.module = importlib.import_module('.'+self.name+'.plugin', 'omg.plugins')
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
        if self.loaded and hasattr(self.module, 'shutdown'):
            self.module.shutdown()
            
    def mainWindowInit(self):
        """Call initMainWindow of the plugin if that method exists."""
        if hasattr(self.module, 'mainWindowInit'):
            self.module.mainWindowInit()
           
    def __str__(self):
        return self.package.NAME


def init():
    global plugins, loadedPlugins, enabledPlugins
    # Dict mapping plugin-names to loaded modules. Contains all plugin-modules which have been loaded
    loadedPlugins = {}
    # List of all plugin-names that are currently enabled
    enabledPlugins = []
    plugins = {}

    from pkg_resources import resource_listdir, resource_exists, resource_isdir
    for plugindir in resource_listdir('omg', 'plugins'):
        try:
            if resource_isdir('omg.plugins', plugindir) and plugindir != '__pycache__':
                plugins[plugindir] = Plugin(plugindir)
        except ImportError:
            if plugindir != '__pycache__':
                # Print an error and continue
                logger.error('Could not load plugin {}'.format(plugindir))
                import traceback
                traceback.print_exc()

    plug_ordered = collections.OrderedDict()
    for pname in sorted(plugins.keys(), key = lambda k: plugins[k].package.NAME):
        plug_ordered[pname] = plugins[pname]
    plugins = plug_ordered



def enablePlugins():
    """Import all plugins which should be loaded and enable them."""
    for pluginName in config.options.main.plugins:
        if pluginName != '':
            if pluginName in plugins:
                plugins[pluginName].enable()
            else: logger.error("could not enable plugin {} since it does not exist – check your config!"
                                .format(pluginName))


def mainWindowInit():
    """Call plugin.mainWindowInit for all enabled plugins."""
    for plugin in plugins.values():
        if plugin.enabled:
            plugin.mainWindowInit()


def shutdown():
    """Shut down all plugins. This will invoke plugin.shutdown on all currently enabled plugins that
    implement the shutdown-method."""
    for plugin in plugins.values():
        plugin.shutdown()
