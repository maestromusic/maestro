# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

"""
This module wraps Python's logging module in a way so that logging works even if that module is not yet configured.
Simply use ``logging.getLogger(name)`` to get a Logger and use it like the usual loggers. Before logging is configured everything will be printed to the console, so call ``init`` as early as possible (but after the config module has been initialized).
"""

import logging, logging.config, os, sys

configured = False # Whether logging has been configured (i.e. init has been successfully called).

class Logger:
    """A logger prints log messages to stderr until logging is configured. Afterwards it wraps a usual Python Logger with the same name."""
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
    """Return a logger with the given name. If *name* is ``None`` use ``"omg"``. Note that this method works even if logging has not been initialized yet."""
    if name is None:
        name = "omg"
    return Logger(name)


def init():
    """Initialize logging from the logging configuration file and the config file. You must initialize the config module first."""
    from omg import config
    if os.path.exists(os.path.join(config.CONFDIR,"logging")):
        logConfFile = os.path.join(config.CONFDIR,"logging")
    else: logConfFile = "logging.conf"

    try:
        # trying to open a nonexistent file with logging.fileconfig leads to the least helpful error message ever...
        if not os.path.exists(logConfFile): 
            raise IOError("File not found")
            
        if not config.options.misc.consoleLogLevel:
            logging.config.fileConfig(logConfFile)
        else:
            # If we must change the configuration from logging.conf, things are ugly: We have to read the file using a ConfigParser, then change the configuration and write it into an io.StringIO-buffer which is finally passed to fileConfig.
            import io, configparser
            logConf = configparser.ConfigParser()
            logConf.read(logConfFile)
            logConf.set('handler_consoleHandler','level',config.options.misc.consoleLogLevel)
            fileLike = io.StringIO()
            logConf.write(fileLike)
            fileLike.seek(0)
            logging.config.fileConfig(fileLike)
            fileLike.close()
    except Exception as e:
        print("ERROR: Could not read logging configuration file '{}'. I will print everything to console. The error message was: {}".format(logConfFile,e))
    else:
        global configured
        configured = True


def shutdown():
    """Shuts down Python's logging system. Further log calls after this method will be printed to stderr."""
    global configured
    logging.shutdown()
    configured = False
