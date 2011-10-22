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
This module wraps Python's logging module in a way so that logging works even if that module is not yet
configured. Simply use ``logging.getLogger(name)`` to get a Logger and use it like the usual loggers.
Before logging is configured everything will be printed to the console, so call ``init`` as early as
possible (but after the config module has been initialized).
"""

import logging, logging.config, os, sys

configured = False # Whether logging has been configured (i.e. init has been successfully called).


class Logger:
    """A logger prints log messages to stderr until logging is configured. Afterwards it wraps a usual Python
    Logger with the same name."""
    def __init__(self,name):
        self.name = name
        if configured:
            self._logger = logging.getLogger(self.name)
        else: self._logger = None

    def log(self,level,message):
        if not configured:
            print(" - ".join([level,self.name,message]),file=sys.stderr)
        else:
            if self._logger is None:
                self._logger = logging.getLogger(self.name)
            # get the integer loglevel from the constants logging.DEBUG, logging.INFO etc.
            self._logger.log(getattr(logging,level),message)
        
    def debug(self,message):
        self.log("DEBUG",message)

    def info(self,message):
        self.log("INFO",message)
        
    def warning(self,message):
        self.log("WARNING",message)
        
    def error(self,message):
        self.log("ERROR",message)
        
    def critical(self,message):
        self.log("CRITICAL",message)

    def exception(self,message):
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
    """Initialize logging from the logging configuration file and the config file. You must initialize the
    config module first.
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
    """Shuts down Python's logging system. Further log calls after this method will be printed to stderr."""
    global configured
    logging.shutdown()
    configured = False
