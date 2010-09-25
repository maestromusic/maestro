# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
# This module handles configuration options from files and from the command line.
import os, logging, configparser, io
import logging.config
import shelve as shelveModule

from . import constants

logger = logging.getLogger("conf")


class ConfigError(Exception):
    
    def __init__(self, msg):
        self.message = msg
    
    def __str__(self):
        return self.message
        
class ConfigOption:
    
    def __init__(self, type, default):
        self.type = type
        self.default = default
        self.value = None
        self.fileValue = None
    
    def getValue(self):
        if self.value is not None:
            return self.value
        elif self.fileValue is not None:
            return self.fileValue
        else:
            return self.default
    
    def updateValue(self, value, updateFileValue = False):
        if not isinstance(value, self.type):
            if self.type in (int, str, bool):
                value = self.type(value)
            elif self.type == list and isinstance(value, str):
                value = [x.strip(" \t") for x in value.split(",")]
            else:
                raise ConfigError("Type of {} does not match type of this option and can't be converted")
        if updateFileValue:
            self.fileValue = value
        else:
            self.value = value

class ConfigSection:
    
    def __init__(self, name):
        self.options = {}
        self.name = name
    
    def __getattr__(self, attr):
        if attr in self.options:
            return self.options[attr].getValue()
        else:
            raise AttributeError("Section {} has no option {}".format(self.name, attr))
    
    def addOption(self, name, type, default):
        self.options[name] = ConfigOption(type, default)
        return self.options[name]
    
    def __str__(self):
        return self.name
        
class Config:
    
    def __init__(self):
        self.sections = {}
        self.shorts = {}
        
    def __getattr__(self, section):
        if section in self.sections:
            return self.sections[section]
        else:
            raise AttributeError("Section {} does not exist".format(section))
    
    def readFromFile(self, filename):
        with open(filename, "r") as file:
            section = "default"
            i = 0   
            for line in file.readlines():
                i += 1
                line = line.strip(" \t\n")
                if len(line) == 0:
                    continue
                if line[0] == "#": #comment line
                    continue
                if line[0] == "[" and line[-1] == "]":
                    section = line[1:-1].strip(" \t")
                    if not section in self.sections:
                        raise ConfigError("File {} tries to access section {} which does not exist".format(filename, section))
                    continue
                try:
                    name, value = (x.strip(" \t") for x in line.split("=", 1))
                except ValueError:
                    raise ConfigError("Syntax error in line {} of file {}: {}".format(i, filename, line))
                self.updateValue(section, name, value, True)
    
    def readConsoleParameters(self, opts):
        for opt, arg in opts:
            if opt in self.shorts:
                self.shorts[opt].updateValue(arg)
            else:
                raise ConfigError("Short option {} not known.".format(opt))
                            
    def updateValue(self, section, name, value, updateFileValue = False):
        if not section in self.sections:
            raise ConfigError("Section {} does not exist".format(section))
        section = self.sections[section]
        if not name in section.options:
            raise ConfigError("Section {} has no option {}".format(section, name))
        section.options[name].updateValue(value, updateFileValue)
        
    def addOption(self, section, name, type, default, shorts = None):
        if section in self.sections:
            sect = self.sections[section]
        else:
            sect = self.sections[section] = ConfigSection(section)
        newOpt = sect.addOption(name, type, default)
        if shorts is not None:
            for s in shorts:
                self.shorts[s] = newOpt
        
omgOptions = {
    "database": [
        # Database driver to use
        ("driver", str, "qtsql"),
        # Database access information
        ("mysql_user", str, ""),
        ("mysql_password", str, ""),
        ("mysql_host", str, "localhost"),
        ("mysql_port", int, 3306),
        # Name of the database
        ("mysql_db", str, "omg"),
    ],
    
    "music": [
        ("collection", str, ".")
    ],
    
    "control": [
        # Interval of the control timer syncing with mpd in milliseconds.
        ("timer_interval", int, 300)
    ],
    
    "mpd": [
        # Host and port where MPD is running
        ("host", str, "localhost"),
        ("port", int, 6600),
    ],

    "tags": [
        # Tags that will be searched, if you type a text without prefix in a searchbox. Use prefixes to search for other tags.
        ("search_tags", list, ["album","performer","conductor","title","lyricist","composer","date","artist"]),
        # Tags which will be totally ignored by this application.
        ("ignored_tags", list, ["tracktotal","disctotal","tracknumber","discnumber"]),
        
        # Order in which tags will be displayed. Must contain title and album! Tags which don't appear in this list will be displayed in arbitrary order after the tags in the list.
        ("tag_order", list,  ["title","artist","album","composer","date","genre","performer","conductor"]),
        
        # Names of the tags which have a special meaning for the application and cannot always be treated generically.
        # This allows to use other strings for the title-tag for example.
        ("title_tag", str, "title"),
        ("album_tag", str, "album"),
        ("date_tag", str, "date"),
    ],
    
    "gui": [
        # Size in pixels of covers
        ("browser_cover_size", int, 40),
        ("large_cover_size", int, 60),
        ("small_cover_size", int, 40),
        ("detail_cover_size", int, 160),
        ("cover_fetcher_cover_size", int, 400),
        
        # size of icons to display
        ("iconsize", int, 16),
        # Maximal number of views in a Browser
        ("max_browser_views", int, 5),
        
        # Application-specific MIME-type for drag and drop operations
        ("mime", str, "application/x-omgelementlist"),
        
        # Tab which will be shown at the beginning ('populate' or 'playlist')
        ("startTab", str, "playlist")
    ],
    
    "log": [
        # Log-level that will be used for console output. Unless this value is None, it will overwrite the value from logging.conf
        ("consoleLogLevel", str, None, ("-v", "--loglevel")),
    ],
    
    "misc": [
        ("printtags_cmd", str, "./printtags.py"),
        ("tagmanip26_cmd", str, os.path.abspath(os.path.join(os.path.split(os.path.split(__file__)[0])[0],"tagmanip26.py"))), # assume tagmanip26.py lives in the same directory as this module
        ("show_ids", bool, False),
    ]
}

_defaultShelveContents = {
    'widget_position': None, # center the window
    'widget_width': 800,
    'widget_height': 600,
    'browser_views': [[['composer','artist','performer']],[['genre'],['composer','artist','performer']]],
}

options = Config()

def init(copts):
    for sect, opts in omgOptions.items():
        for opt in opts:
            options.addOption(sect, *opt)
    options.readFromFile(constants.CONFIG)
    options.readConsoleParameters(copts)
    
    if os.path.exists(os.path.join(constants.CONFDIR,"logging.conf")):
        logConfFile = os.path.join(constants.CONFDIR,"logging.conf")
    else: logConfFile = "logging.conf"
    
    if  options.log.consoleLogLevel is None:
        logging.config.fileConfig(logConfFile)
    else:
        # If we must change the configuration from logging.conf, things are ugly: We have to read the file using a ConfigParser, then change the configuration and write it into a io.StringIO-buffer which is finally passed to fileConfig.
        logConf = configparser.ConfigParser()
        logConf.read(logConfFile)
        logConf.set('handler_consoleHandler','level',options.log.consoleLogLevel)
        fileLike = io.StringIO()
        logConf.write(fileLike)
        fileLike.seek(0)
        logging.config.fileConfig(fileLike)
        fileLike.close()
        
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