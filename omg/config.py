# -*- coding: utf-8 -*-
# Copyright 2009 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

"""
The config module has three tasks:
- Read the configuration file (constants.CONF) and store the options during execution.
- Manage the shelve.
- Configure the logging system based on the file logging.conf (in constants.CONFDIR or, if this file does not exist, in the program's main directory) and on the configuration file.

This module must be initialized via the init-method.

Use config.get and config.set to access config-variables. Use config.shelve to access the shelve.
"""

import configparser, logging, io
import logging.config
import os.path
import shelve as shelveModule

from omg import constants

_defaultOptions = {
    "database": {
        # Database driver to use
        "driver": "qtsql",
        # Database access information
        "mysql_user":"",
        "mysql_password":"",
        "mysql_host":"localhost",
        "mysql_port":"3306",
        # Name of the database
        "mysql_db":"omg"
    },
    
    "control": {
        # Interval of the control timer syncing with mpd in milliseconds.
        "timer_interval": "300"
    },
    
    "mpd": {
        # Host and port where MPD is running
        "host": "localhost",
        "port": "6600"
    },

    "tags": {
        # Tags that will be searched, if you type a text without prefix in a searchbox. Use prefixes to search for other tags.
        "search_tags":"album,performer,conductor,title,lyricist,composer,date,artist",
        # Tags which will be totally ignored by this application.
        "ignored_tags":"encodedby,tracktotal,disctotal,tracknumber,discnumber",
        
        # Order in which tags will be displayed. Must contain title and album! Tags which don't appear in this list will be displayed in arbitrary order after the tags in the list.
        "tag_order": "title,album,composer,artist,performer,conductor,date,genre",
        
        # Names of the tags which have a special meaning for the application and cannot always be treated generically.
        # This allows to use other strings for the title-tag for example.
        "title_tag": "title",
        "album_tag": "album",
        "date_tag": "date",
    },
    
    "gui": {
        # Size in pixels of covers
        "browser_cover_size": 40,
        "large_cover_size": 60,
        "small_cover_size": 40,
        "detail_cover_size": 160,
        "cover_fetcher_cover_size": 400,
        
        # Maximal number of views in a Browser
        "max_browser_views": 5,
        
        # Application-specific MIME-type for drag and drop operations
        "mime": "application/x-omgelementlist",
        
        # Tab which will be shown at the beginning ('populate' or 'playlist')
        "startTab": "playlist"
    },
    
    "log": {
        # Log-level that will be used for console output. Unless this value is None, it will overwrite the value from logging.conf
        "consoleLogLevel": None,
    },
    
    "misc": {
        "printtags_cmd":"./printtags.py",
        "tagmanip26_cmd":os.path.abspath(os.path.join(os.path.split(os.path.split(__file__)[0])[0],"tagmanip26.py")), # assume tagmanip26.py lives in the same directory as this module
        "show_ids":0,
    }
}

_defaultShelveContents = {
    'widget_position': None, # center the window
    'widget_width': 800,
    'widget_height': 600,
    'browser_views': [[['composer','artist','performer']],[['genre'],['composer','artist','performer']]],
}

_config = configparser.RawConfigParser()
shelve = None

# Provide methods to overwrite default options (for example via command-line parameters)
get = _config.get
set = _config.set


def init(optionOverride = {}):
    """Initialize the config-module, i.e. perform the following steps:
    - Store the default options
    - Overwrite them with the options from the config-file
    - Overwrite the options with by <optionOverride> (this is for example used for command-line parameters)
    - Initialize the logging system
    - Initialize the shelve. If a key from _defaultShelveContents is not found in the shelve write the corresponding default value into it.
    """
    
    # Initialize options
    _storeOptions(_defaultOptions)
    _config.read(constants.CONFIG)
    _storeOptions(optionOverride)

    # Initialize logging
    if os.path.exists(os.path.join(constants.CONFDIR,"logging.conf")):
        logConfFile = os.path.join(constants.CONFDIR,"logging.conf")
    else: logConfFile = "logging.conf"
    
    if _config.get('log','consoleLogLevel') is None:
        logging.config.fileConfig(logConfFile)
    else:
        # If we must change the configuration from logging.conf, things are ugly: We have to read the file using a ConfigParser, then change the configuration and write it into a io.StringIO-buffer which is finally passed to fileConfig.
        logConf = configparser.ConfigParser()
        logConf.read(logConfFile)
        logConf.set('handler_consoleHandler','level',_config.get('log','consoleLogLevel'))
        fileLike = io.StringIO()
        logConf.write(fileLike)
        fileLike.seek(0)
        logging.config.fileConfig(fileLike)
        fileLike.close()
        
    # Now open the shelve
    shelveDir = os.path.dirname(constants.SHELVE)
    if not os.path.exists(shelveDir):
        logging.get('omg').info("Creating shelve directory '{0}'".format(shelveDir))
        os.makedirs(shelveDir)
    global shelve
    shelve = shelveModule.open(constants.SHELVE)

    for key,option in _defaultShelveContents.items():
        if key not in shelve:
            shelve[key] = option
    return shelve 


def _storeOptions(options):
    """Store the options from the given dictionary. <options> must map section names to dictionaries mapping option names to option values (confer _defaultOptions). If an option from <options> already exists, it will be overwritten."""
    for section,configs in options.items():
        if not _config.has_section(section):
            _config.add_section(section)
        for key, value in configs.items():
            _config.set(section, key, value)