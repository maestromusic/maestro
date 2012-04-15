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
This module wraps Python's :mod:`logging` module in a way so that logging works even if that module is not
yet configured. Simply use ``logging.getLogger(name)`` to get a Logger and use it like the usual loggers::

    logger = logging.getLogger(__name__) # __name__ is the name of the current module
    logger.debug("Test")

Before logging is configured everything will be printed to the console, so call :func:`init` as early as
possible (but after the config module has been initialized).
"""

import logging, logging.config, os, sys

configured = False # Whether logging has been configured (i.e. init has been successfully called).


class Logger:
    """A logger prints log messages to ``stderr`` until logging is configured. Afterwards it wraps a usual
    Python :class:`Logger <logging.Logger>` with the same name."""
    def __init__(self,name):
        self.name = name
        if configured:
            self._logger = logging.getLogger(self.name)
        else: self._logger = None

    def log(self,level,message):
        """Log a message on the given level. *level* must be a string from
        ``['DEBUG','INFO',WARNING','ERROR','CRITICAL']``."""
        if not configured:
            print(" - ".join([level,self.name,message]),file=sys.stderr)
        else:
            if self._logger is None:
                self._logger = logging.getLogger(self.name)
            # get the integer loglevel from the constants logging.DEBUG, logging.INFO etc.
            self._logger.log(getattr(logging,level),message)
        
    def debug(self,message):
        """Log a debug message."""
        self.log("DEBUG",message)

    def info(self,message):
        """Log an info message."""
        self.log("INFO",message)
        
    def warning(self,message):
        """Log a warning message."""
        self.log("WARNING",message)
        
    def error(self,message):
        """Log an error message."""
        self.log("ERROR",message)
        
    def critical(self,message):
        """Log a critical error message."""
        self.log("CRITICAL",message)

    def exception(self,message):
        """Log an exception message. Information about the exception will be fetched using :mod:`traceback`.
        """
        if not configured:
            type, value, tb = sys.exc_info()
            self.error(message + " Exception: {}".format(value))
            import traceback
            traceback.print_tb(tb)
            del tb # confer sys.exc_info
        else:
            if self._logger is None:
                self._logger = logging.getLogger(self.name)
            self._logger.exception(message)
        
        
def getLogger(name=None):
    """Return a logger with the given name. If *name* is ``None`` use ``"omg"``. Note that this method works
    even if logging has not been initialized yet."""
    if name is None:
        name = "omg"
    return Logger(name)


def init():
    """Initialize logging according to the config variable ``config.storage.main.logging``. Of course, you
    must initialize the config module first.
    """
    from omg import config
    
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
