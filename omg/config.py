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

from PyQt4 import QtCore
from . import constants

logger = logging.getLogger("conf")


class ConfigError(Exception):
    
    def __init__(self, msg):
        self.message = msg
    
    def __str__(self):
        return self.message
        
class ConfigOption:
    
    def __init__(self, type, default, description):
        self.type = type
        self.default = default
        self.value = None
        self.fileValue = None
        self.description = description
    
    def getValue(self):
        if self.value is not None:
            return self.value
        elif self.fileValue is not None:
            return self.fileValue
        else:
            return self.default
    
    def updateValue(self, value, updateFileValue = False):
        if not isinstance(value, self.type):
            if self.type == bool:
                # bool("0") or bool("False") are True, but we want them to be false as this is what you type in a configuration file to make a variable false.
                if value == "0" or value.lower() == "false":
                    value = False
                else: value = self.type(value)
            elif self.type in (int, str):
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
    
    def addOption(self, name, type, default, description = None):
        self.options[name] = ConfigOption(type, default, description)
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
        
    def addOption(self, section, name, type, default, shorts = None, description = None):
        if section in self.sections:
            sect = self.sections[section]
        else:
            sect = self.sections[section] = ConfigSection(section)
        newOpt = sect.addOption(name, type, default, description = description)
        if shorts is not None:
            for s in shorts:
                self.shorts[s] = newOpt
                
def initOmgOptions(options):

    # No need to translate the strings in this method, as it is executed before any translators have been loaded.
    options.addOption("i18n",       "locale",           str,    QtCore.QLocale.system().name(), shorts=("-l","--locale"), description="The locale used by omg (e.g. de_DE).")
    options.addOption("database",   "driver",           str,    "qtsql"         )
    options.addOption("database",   "mysql_user",       str,    ""              )
    options.addOption("database",   "mysql_password",   str,    ""              )
    options.addOption("database",   "mysql_host",       str,    "localhost"     )
    options.addOption("database",   "mysql_port",       int,    3306            )
    options.addOption("database",   "mysql_db",         str,    "omg"           )
    
    
    options.addOption("music",      "collection",       str,    "."             , description="Collection base directory")
    options.addOption("music",      "extensions",       list,    ["flac",
                                                                  "m4a",
                                                                  "mp3",
                                                                  "mp4",
                                                                  "mpc",
                                                                  "oga",
                                                                  "ogg",
                                                                  "spx"]        , description="Recognized file extensions")
    
    options.addOption("control",    "timer_interval",   int,    300             , description="Interval of mpd synchronization")
    
    options.addOption("mpd",        "host",             str,    "localhost"     )
    options.addOption("mpd",        "port",             int,    6600            )
    
    options.addOption("tags",       "search_tags",      list,   ["album",
                                                                 "performer",
                                                                 "conductor",
                                                                 "title",
                                                                 "lyricist",
                                                                 "composer",
                                                                 "date",
                                                                 "artist"]      , description="Tags that will be searched, if you type a text without prefix in a searchbox. Use prefixes to search for other tags.")
    options.addOption("tags",       "ignored_tags",     list,   ["tracktotal",
                                                                 "disctotal",
                                                                 "tracknumber",
                                                                 "discnumber",
                                                                 "compilation"]  )
    options.addOption("tags",       "tag_order",        list,   ["title",
                                                                 "artist",
                                                                 "album",
                                                                 "composer",
                                                                 "date",
                                                                 "genre",
                                                                 "peformer",
                                                                 "conductor"]   , description="Order in which tags will be displayed. Must contain title and album! Tags which don't appear in this list will be displayed in arbitrary order after the tags in the list.")
    options.addOption("tags",       "title_tag",        str,    "title"         )
    options.addOption("tags",       "album_tag",        str,    "album"         )
    options.addOption("tags",       "date_tag",         str,    "date"          )
    
    options.addOption("gui",        "browser_cover_size",int,   40              )
    options.addOption("gui",        "small_cover_size", int,    40              )
    options.addOption("gui",        "detail_cover_size",int,    160             )
    options.addOption("gui",        "large_cover_size", int,    60              )
    options.addOption("gui",        "cover_fetcher_cover_size",int,400          )
    options.addOption("gui",        "iconsize",         int,    16              )
    options.addOption("gui",        "max_browser_views",int,    5               )
    options.addOption("gui",        "mime",             str,    "application/x-omgelementlist")
    options.addOption("gui",        "startTab",         str,    "playlist"      )
    
    options.addOption("log",        "consoleLogLevel",  str,    None,           shorts=("-v", "--loglevel"))
    
    options.addOption("misc",       "tagmanip26_cmd",   str,    os.path.abspath(os.path.join(os.path.split(os.path.split(__file__)[0])[0],"tagmanip26.py")))
    options.addOption("misc",       "tags_python2_cmd", str,    os.path.abspath(os.path.join(os.path.split(__file__)[0],"realfiles2/tags_python2.py")))
    options.addOption("misc",       "show_ids",         bool,   False           )

_defaultShelveContents = {
    'widget_position': None, # center the window
    'widget_width': 800,
    'widget_height': 600,
    'browser_views': [[['composer','artist','performer']],[['genre'],['composer','artist','performer']]],
}

options = Config()

def init(copts):
    initOmgOptions(options)
    options.readFromFile(constants.CONFIG)
    options.readConsoleParameters(copts)
    
    if os.path.exists(os.path.join(constants.CONFDIR,"logging.conf")):
        logConfFile = os.path.join(constants.CONFDIR,"logging.conf")
    else: logConfFile = "logging.conf"
    
    if  options.log.consoleLogLevel is None:
        logging.config.fileConfig(logConfFile)
    else:
        # If we must change the configuration from logging.conf, things are ugly: We have to read the file using a ConfigParser, then change the configuration and write it into an io.StringIO-buffer which is finally passed to fileConfig.
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
