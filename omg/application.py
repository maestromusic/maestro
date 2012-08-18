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

"""
This module controls the startup and finishing process of OMG. The init method may be used to initialize
OMG's framework without starting a GUI.
"""

import sys, os, fcntl, getopt

from PyQt4 import QtCore, QtGui, QtNetwork
from PyQt4.QtCore import Qt

from . import config, logging, constants

logger = None # Will be set when logging is initialized
        
# The application's main window
mainWindow = None

# The application's undo stack
stack = None

# The application's QNetworkAccessManager
network = None

# Store translators so that they are not garbage-collected
_translators = []


class ChangeEvent:
    """Abstract super class for all changeevents."""
    pass


class ChangeEventDispatcher(QtCore.QObject):
    _changes = QtCore.pyqtSignal(ChangeEvent)
    
    def __init__(self):
        QtCore.QObject.__init__(self)
        
    def emit(self,event):
        if not stack.inMacro():
            self._changes.emit(event)
        else: stack.addEvent(self._changes,event)
    
    def connect(self,handler):
        self._changes.connect(handler)
        
    def disconnect(self,handler):
        self._changes.disconnect(handler)
        

dispatcher = None
 

def run(cmdConfig=[],type='gui',exitPoint=None):
    """This is the entry point of OMG. With the default arguments OMG will start the GUI. Use init if you
    only want to initialize the framework without starting the GUI.
    
    *cmdConfig* is a list of options given on the command line that will
    overwrite the corresponding option from the file or the default. Each list item has to be a string like
    ``main.collection=/var/music``.
    
    *type* is determines how the application should be initialized and run: "gui" will start the usual
    application, "console" will initialize the framework without starting the the GUI. "test" is similar
    to "console" but will connect to an in-memory SQLite-database instead of the usual database. All tables
    will be created and empty in this database.
    
    Using the optional argument *exitPoint* you may also initialize only part of the framework. Allowed
    values are (in this order):
    
        - 'config':    Initialize only config
        - 'database':  Stop after database connection has been established
        - 'tags':      Stop after tags module has been initialized (this needs a db connection)
        - 'noplugins': Stop before plugins would be loaded
        - 'nogui':     Stop right before the GUI would be created (plugins are enabled at this point)
        
    If *exitPoint* is not None, this method returns the created QApplication-instance.
    """
    handleCommandLineOptions(cmdConfig)
    
    # Some Qt-classes need a running QApplication before they can be created
    app = QtGui.QApplication(sys.argv)
    app.setApplicationName("OMG")

    # Initialize config and logging
    config.init(cmdConfig,testMode=type=='test')
    
    # Initialize logging as early as possible -- but after the config variables have been read.
    logging.init()
    global logger
    logger = logging.getLogger("omg")
    logger.debug("START")
                     
    if exitPoint == 'config':
        return app
    
    # Lock the lockfile to prevent a second OMG-instance from starting.
    if type == 'gui':
        lock()
        
    # Check for a collection directory
    if type == 'gui' and config.options.main.collection == '':
        logger.error("No collection directory defined.")
        runInstaller()
    
    loadTranslators(app,logger)

    # Initialize dispatcher
    global dispatcher
    dispatcher = ChangeEventDispatcher()
    
    if config.options.misc.debug_events:
        def _debugAll(event):
            logger.debug("EVENT: " + str(event))
        dispatcher.connect(_debugAll)
        
    # Initialize database
    if type == 'test':
        config.options.database.type = 'sqlite'
        config.options.database.prefix = 'test'
        config.options.database.sqlite_path = ':memory:'
    from . import database
    try:
        database.connect()
    except database.sql.DBException as e:
        logger.error("I cannot connect to the database. Did you provide the correct information in the"
                     " config file? SQL error: {}".format(e.message))
        if type == 'gui':
            runInstaller()
            
    if type == 'test':
        from omg.database import tables
        for table in tables.tables:
            table.create()
            
    if exitPoint == 'database':
        return app
        
    # Initialize tags
    from .core import tags,flags
    try:
        tags.init()
    except RuntimeError:
        if type == 'gui':
            runInstaller()
        else: sys.exit(1)

    if type == 'gui':
        # Weird things might happen if these tagtypes are external
        if not tags.get(config.options.tags.title_tag).isInDB():
            logger.error("Title tag '{}' is missing in tagids table.".format(config.options.tags.title_tag))
            runInstaller()
        if not tags.get(config.options.tags.album_tag).isInDB():
            logger.error("Album tag '{}' is missing in tagids table.".format(config.options.tags.album_tag))
            runInstaller()
            
        # In most test scripts these caches would only be overhead.
        database.cacheTagValues()
        
    flags.init()
    
    if exitPoint == 'tags':
        return app
    
    # Initialize stack before levels are initialized    
    global stack
    stack = UndoStack()
    
    # Load and initialize remaining modules
    from .core import levels
    levels.init()
    from . import resources, search
    from .core import covers
    search.init()
    covers.init()
    
    from . import filebackends
    from .filebackends import filesystem as fsBackend
    
    global network
    network = QtNetwork.QNetworkAccessManager()
    
    if type == 'test' or exitPoint == 'noplugins':
        return app
    
    # Load Plugins
    from . import plugins
    plugins.init()
    plugins.enablePlugins()
    
    if type != 'gui':
        return app
        
    from . import filesystem
    filesystem.init()

    # Create GUI
    # First import all modules that want to add WidgetData
    from .gui import filesystembrowser, editor, browser, tageditor, mainwindow, playback, playlist
    
    from .gui.delegates import configuration as delegateconfiguration
    global mainWindow
    
    delegateconfiguration.load()
    
    mainWindow = mainwindow.MainWindow()
    plugins.mainWindowInit()
    
    # Launch application
    mainWindow.show()
    returnValue = app.exec_()
    
    # Close operations
    logger.debug('main application quit')
    filesystem.shutdown()
    search.shutdown()
    mainWindow.saveLayout()
    delegateconfiguration.save()
    plugins.shutdown()
    covers.shutdown()
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
        fileDescriptor = os.open(lockFile,os.O_WRONLY | os.O_CREAT)
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


def init(cmdConfig=[],type='console',exitPoint='noplugins'):
    """Initialize OMG's framework (database, tags etc.) but do not run a GUI. Use this for tests on the
    terminal:

        >>> from omg import application
        >>> application.init()
        >>> from omg.core import tags
        >>> tags.tagList
        ["title", "artist", "album", ...]
    
    If *exitPoint* is not None, return the created QApplication-instance.
    Actually this method is the same as run, but with different default arguments.
    """
    return run(cmdConfig,type,exitPoint)


def runInstaller():
    """Run the graphical installer."""
    os.execl(sys.executable, os.path.basename(sys.executable), "-m", "omg.install")
    
    
class UndoStack(QtGui.QUndoStack):
    def __init__(self):
        super().__init__()
        self._macroDepth = 0
        self._eventQueue = []
    
    def inMacro(self):
        return self._macroDepth > 0
    
    def beginMacro(self,text):
        super().beginMacro(text)
        self._macroDepth += 1
        
    def endMacro(self):
        super().endMacro()
        self._macroDepth -= 1
        if self._macroDepth == 0:
            for signal,event in self._eventQueue:
                signal.emit(event)
            self._eventQueue = []
            
    def addEvent(self,signal,event):
        self._eventQueue.append((signal,event))
            
        
    
if __name__ == "__main__":
    run()
