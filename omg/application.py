# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
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

"""
This module controls the startup and finishing process of OMG. The run method may also be used to initialize
OMG's framework without starting a GUI.
"""

import sys, os, fcntl, getopt

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from omg import config, logging, database, constants

# The application's main window
mainWindow = None

global logger
        
# Store translators so that they are not garbage-collected
_translators = []


def run(cmdConfig=[],exitPoint="nogui",console=True):
    """This method serves two purposes: It is the entry point for OMG and it is used to initialize OMG's
    framework on the console and without GUI for debugging. Using this method on the console works like this:

        >>> from omg import application, tags
        >>> application.run()
        >>> tags.tagList
        ["title", "artist", "album", ...]
        
    Then using this method on the console, use the parameter *exitPoint* to determine how much of the
    framework should be initialized. Note that the default parameters are chosen to save work on the console
    and are not the values necessary to get the usual graphical application.
    
        * cmdConfig: is a list of options given on the command line that will overwrite the corresponding
          option from the file or the default. Each list item has to be a string like
          ``main.collection=/var/music``.
        * exitPoint: Determines when to stop the startup process. Set this to None to run OMG's usual GUI.
          Other allowed values are 'database','tags' and 'nogui'. The run script will stop after the database
          connection has been established, after the tags module has been initialized or just before the GUI 
          would be created, respectively.
        * console: Set this to True on the console to turn off the lockfile and the (graphical) installer.
    """
    handleCommandLineOptions(cmdConfig)
    
    # Some Qt-classes need a running QApplication before they can be created
    app = QtGui.QApplication(sys.argv)

    # Initialize config and logging
    config.init(cmdConfig)
    # Initialize logging as early as possible -- but after the config variables have been read.
    logging.init()
    global logger
    logger = logging.getLogger("omg")
    logger.debug("START")
    
    # Lock the lockfile to prevent a second OMG-instance from starting.
    if not console:
        lock()
    
    # Check for a collection directory
    if config.options.main.collection == '':
        logger.error("No collection directory defined.")
        if not console:
            runInstaller()
        else: sys.exit(1)
    
    loadTranslators(app,logger)

    # Initialize database
    try:
        database.connect()
    except database.sql.DBException as e:
        logger.error("I cannot connect to the database. Did you provide the correct information in the config"
                     " file? MySQL error: {}".format(e.message))
        if not console:
            runInstaller()
        else: sys.exit(1)
    if exitPoint == 'database':
        return
        
    # Initialize tags
    from omg import tags,flags
    try:
        tags.init()
    except RuntimeError:
        if not console:
            runInstaller()
        else: sys.exit(1)
    flags.init()
    if exitPoint == 'tags':
        return
        
    # Load and initialize remaining modules
    from omg.models import levels
    levels.init()
    from omg import resources, search
    search.init()
    
    # Load Plugins
    from . import plugins
    plugins.init()
    plugins.enablePlugins()
    
    if exitPoint == 'nogui':
        return
        
    from . import filesystem
    #filesystem.init()
        
    # Create GUI
    # First import all modules that want to add WidgetData
    from .gui import filesystembrowser, editor, browser, tageditor, mainwindow, playback, playlist
    from .gui.delegates import configuration as delegateconfiguration
    global mainWindow
    
    delegateconfiguration.load()
    
    from . import player
    player.init()
    mainWindow = mainwindow.MainWindow()
    plugins.mainWindowInit()
    
    # Launch application
    mainWindow.show()
    returnValue = app.exec_()
    
    # Close operations
    logger.debug('main application quit')
    #filesystem.shutdown()
    search.shutdown()
    mainWindow.saveLayout()
    delegateconfiguration.save()
    plugins.shutdown()
    config.shutdown()
    logging.shutdown()
    sys.exit(returnValue)


def handleCommandLineOptions(cmdConfig):
    """Parse command line options and act accordingly (e.g. print version and exit). Add config option
    overwrites (with the --config/-c option) to the list *cmdConfig*."""
    opts, args = getopt.getopt(sys.argv[1:],
        "vVc:",
        ['version','config=', 'install'])

    for opt,arg in opts:
        if opt in ('-v','-V', '--version'):
            print('This is OMG version {}. Nice to meet you.'.format(constants.VERSION))
            sys.exit(0)
        elif opt in ('-c','--config'):
            cmdConfig.append(arg)
        elif opt == '--install':
            runInstaller()
        else:
            logger.warning("Unknown option '{}'.".format(opt))

         
def lock():
    """Lock the lockfile so that no other instance can be started. Quit the application if it is already
    locked."""
    # Confer http://packages.python.org/tendo/_modules/tendo/singleton.html#SingleInstance
    lockFile = os.path.join(config.CONFDIR,'lock')
    try:
        # For a long time the built-in function open was used here. But one day it stopped working oO
        fileDescriptor = os.open(lockFile,os.O_WRONLY| os.O_CREAT)
    except IOError:
        logger.error("Cannot open lock file {}".format(lockFile))
        sys.exit(-1)
    try:
        fcntl.lockf(fileDescriptor,fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        logger.error("Another instance is already running, quitting.")
        sys.exit(-1)


def loadTranslators(app,logger):
    """Load a translator for Qt's strings and one for OMG's strings."""
    from . import translations
    # Try up to two different locales
    for translator in _translators:
        app.removeTranslator(translator)
    locales = [QtCore.QLocale.system().name()]
    if config.options.i18n.locale:
        locales.insert(0,config.options.i18n.locale)
        QtCore.QLocale.setDefault(QtCore.QLocale(config.options.i18n.locale))
        
    # Install a translator for Qt's own strings
    qtTranslator = QtCore.QTranslator(app)
    translatorDir = QtCore.QLibraryInfo.location(QtCore.QLibraryInfo.TranslationsPath)
    for locale in locales:
        if locale == 'en':
            continue # This is the default and qt_en does therefore not exist
        translatorFile = "qt_" + locale
        if qtTranslator.load(translatorFile,translatorDir):
            app.installTranslator(qtTranslator)
            _translators.append(qtTranslator)
            break
        else: logger.warning("Unable to load Qt's translator file {} from directory {}."
                                .format(translatorFile,translatorDir))

    # Load a translator for our strings
    translator = QtCore.QTranslator(app)
    translatorDir = os.path.join(":omg/i18n")
    for locale in locales:
        translatorFile = 'omg.'+locale
        if translator.load(translatorFile,translatorDir):
            app.installTranslator(translator)
            _translators.append(translator)
            break
        else: logger.warning("Unable to load translator file {} from directory {}."
                                .format(translatorFile,translatorDir))


def runInstaller():
    """Run the graphical installer."""
    os.execl(sys.executable, os.path.basename(sys.executable), "-m", "omg.install")
    
    
if __name__ == "__main__":
    run(exitPoint=None,console=False) 
