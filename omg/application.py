# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

"""
This module controls the startup and finishing process of OMG. :func:`run` runs the application while
:func:`init` only initializes the most basic modules without starting a graphical interface.
"""

import sys, os, fcntl

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from omg import config, logging, database

# The application's main window
mainWindow = None

global logger

def init(cmdConfig = [],initTags=True,testDB=False):
    """Initialize the application, modules (config, logging, database and tags) but do not create a GUI or
    load any plugins. Return the QApplication instance. This is useful for scripts which need OMG's framework,
    but not its GUI and for testing (or playing around) in Python's shell::

        >>> from omg import application, tags
        >>> application.init()
        <PyQt4.QtGui.QApplication object at 0xb7569f5c>
        >>> tags.tagList
        ["title", "artist", "album", ...]

    *cmdOptions* is a list of options given on the command line that will overwrite the corresponding option
    from the file or the default. Each list item has to be a string like ``main.collection=/var/music``.
    If *initTags* is False, the tag module will not be initialized.
    If *testDB* is True, the database connection will be build using :func:`database.testConnect`.
    Warning: In this case you may want to set *initTags* to False because the test database is usually empty.
    """
    # Some Qt-classes need a running QApplication before they can be created
    app = QtGui.QApplication(sys.argv)

    # Switch to the application's directory (one level above this file's directory)
    if os.path.dirname(__file__):
        os.chdir(os.path.dirname(__file__))
    os.chdir("../")

    # Initialize config and logging
    config.init(cmdConfig)
    logging.init()
    global logger
    logger = logging.getLogger("omg")
    logger.debug("START")
    
    # Load translators
    qtTranslator = QtCore.QTranslator(app) # Translator for Qt's own strings
    translatorDir = QtCore.QLibraryInfo.location(QtCore.QLibraryInfo.TranslationsPath)
    translatorFile = "qt_" + QtCore.QLocale.system().name()
    if qtTranslator.load(translatorFile,translatorDir):
        app.installTranslator(qtTranslator)
    else: logger.warning("Unable to load Qt's translator file {} from directory {}."
                            .format(translatorFile,translatorDir))

    translator = QtCore.QTranslator(app) # Translator for our strings
    translatorDir = os.path.join(os.getcwd(),'i18n')
    translatorFile = 'omg.'+config.options.i18n.locale
    if translator.load(translatorFile,translatorDir):
        app.installTranslator(translator)
    else: logger.warning("Unable to load translator file {} from directory {}."
                            .format(translatorFile,translatorDir))

    # Initialize remaining modules
    if not testDB:
        database.connect()
    else: database.testConnect()

    if initTags:
        from omg import tags
        tags.init()

    return app


def run(cmdConfig = []):
    """Run OMG. *cmdOptions* is a list of options given on the command line that will overwrite the
    corresponding option from the file or the default. Each list item has to be a string like
    ``main.collection=/var/music``.
    """
    app = init(cmdConfig)
    
    # Lock the lockfile to prevent a second OMG-instance from starting.
    # Confer http://packages.python.org/tendo/_modules/tendo/singleton.html#SingleInstance
    lockFile = os.path.join(config.CONFDIR,'lock')
    try:
        fileDescriptor = open(lockFile,'w')
    except IOError:
        logger.error("Cannot open lock file {}".format(lockFile))
        sys.exit(-1)
    try:
        fcntl.lockf(fileDescriptor,fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        logger.error("Another instance is already running, quitting.")
        sys.exit(-1)
    
    # Load remaining modules
    from omg import tags, search
    search.init()

    # Load Plugins
    from omg import plugins
    plugins.enablePlugins()

    # Create GUI
    # First import all modules that want to add WidgetData
    import omg.gui.filesystembrowser
    import omg.gui.editor
    import omg.gui.browser
    import omg.gui.tageditor
    from omg.gui import mainwindow
    global mainWindow
    mainWindow = mainwindow.MainWindow()
    plugins.mainWindowInit()

    # Launch application
    mainWindow.show()
    returnValue = app.exec_()

    # Close operations
    search.shutdown()
    mainWindow.saveLayout()
    plugins.shutdown()
    #sync.shutdown()
    config.shutdown()
    logging.shutdown()

    sys.exit(returnValue)
