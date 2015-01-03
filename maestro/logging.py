# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2015 Martin Altmayer, Michael Helmling
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
This module wraps Python's :mod:`logging` module in a way so that logging works even if that module is not
yet configured. To log messages use one of the methods debug, info, warning, error, critical, exception:

    logging.debug(__name__, message)
    
The first argument should always be __name__ to include the module name into the log. For convenience
it is possible to create a Logger that stores the name permanently:

    logger = logging.getLogger(__name__)
    logger.debug(message) # or info, warning, etc.
    
Before logging is configured everything will be printed to the console, so call :func:`init` as early as
possible (but after the config module has been initialized).
"""

import sys, functools, os
import logging, logging.config

configured = False # Whether logging has been configured (i.e. init has been successfully called).


def init():
    """Initialize logging according to the config variable ``config.storage.main.logging``. Of course, you
    must initialize the config module first.
    """
    from . import config
    
    # Typically log files are created within this directory, so make sure it exists.
    os.makedirs(os.path.join(os.path.expanduser("~"), ".config", "maestro"), exist_ok=True)
    
    logging.config.dictConfig(config.storage.main.logging)
    
    if config.options.misc.consoleLogLevel:
        logging.config.dictConfig({
                "version": 1,
                "incremental": True,
                "handlers": {"consoleHandler": {"level": config.options.misc.consoleLogLevel}}
            })

    global configured
    configured = True


def shutdown():
    """Shuts down Python's logging system. This module's logging functions will still work, but all further
    messages will be printed to ``stderr``."""
    global configured
    logging.shutdown()
    configured = False

    
def log(name, level, message):
    """Log a message on the logger called *name* using the given log level."""
    if not configured:
        print(" - ".join([level, name, message]), file=sys.stderr)
    else:
        # get the integer loglevel from the constants logging.DEBUG, logging.INFO etc.
        logging.log(getattr(logging, level), "{} - {}".format(name, message))
    
def debug(name, message):
    """Log a debug message on the logger called *name*."""
    log(name, "DEBUG", message)

def info(name, message):
    """Log an info message on the logger called *name*."""
    log(name, "INFO", message)
    
def warning(name, message):
    """Log a warning on the logger called *name*."""
    log(name, "WARNING", message)
    
def error(name, message):
    """Log an error on the logger called *name*."""
    log(name, "ERROR", message)
    
def critical(name, message):
    """Log a critical error on the logger called *name*."""
    log(name, "CRITICAL", message)
    
def exception(name, message):
    """Log an exception together with a string *message* on the logger called *name*.
    Information about the exception will be fetched using :mod:`traceback`."""
    if not configured:
        type, value, tb = sys.exc_info()
        error(name, message + " Exception: {}".format(value))
        import traceback
        traceback.print_tb(tb)
        del tb # confer sys.exc_info
    else:
        logging.exception("{} - {}".format(name, message))


class Logger:
    """This object is initialized with a logger name once and then provides the usual logging methods
    without that the name must be specified every time."""
    def __init__(self, name):
        self.name = name
        # Add logging methods to Logger class
        for method in [log, debug, info, warning, error, critical, exception]:
            setattr(self, method.__name__, functools.partial(method, name))

def getLogger(name):
    """Create a Logger-instance with the given name."""
    return Logger(name)
        

def addHandler(handler):
    """See https://docs.python.org/3/library/logging.html#logging.Logger.addHandler"""
    logging.getLogger().addHandler(handler)


def removeHandler(handler):
    """See https://docs.python.org/3/library/logging.html#logging.Logger.removeHandler"""
    logging.getLogger().removeHandler(handler)
    
