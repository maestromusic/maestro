# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

import os, logging
from . import constants

logger = logging.getLogger("conf")


class ConfigError(Exception):
    
    def __init__(self, msg):
        self.message = msg
        
class ConfigOption:
    
    def __init__(self, type, default):
        self.type = type
        self.default = default
        self.value = default
        self.fileValue = default
    
    def updateValue(self, value, updateFileValue = False):
        if not isinstance(value, self.type):
            if self.type in (int, str, bool):
                value = self.type(value)
            elif self.type == list and isinstance(value, str):
                value = map(lambda x: x.split(" \t"), value.split(","))
            else:
                raise ConfigError("Type of {} does not match type of this option and can't be converted")
        self.value = value
        if updateFileValue:
            self.fileValue = value

class ConfigSection:
    
    def __init__(self, name):
        self.options = []
        self.name = name
    
    def __getattr__(self, attr):
        if attr in self.options:
            return self.options[attr]
        else:
            raise AttributeError("Section {} has no option {}".format(self.name, attr))
    
    def addOption(self, name, type, default):
        self.options[name] = ConfigOption(type, default)
        
class Config:
    
    def __init__(self):
        self.sections = {}
        
    def __getattr__(self, section):
        if section in self.sections:
            return self.sections[section]
        else:
            raise AttributeError("Section {} does not exist".format(section))
    
    def readFromFile(self, filename):
        with open(filename, "r") as file:
            section = "default"
            i = 1
            for line in file.readlines():
                i += 1
                line = line.strip(" \t")
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
                    raise ConfigError("Syntax error in line {} of file {}".format(i, file))
                self.sections[section][name].updateValue(value, True)
                        
    
    def addOption(self, section, name, type, default):
        if section in self.sections:
            sect = self.sections[section]
        else:
            sect = self.sections[section] = ConfigSection(section)
        sect.addOption(type, default)
        
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
        ("cover_fetcher_cover_size", int, 400)
        
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
        ("consoleLogLevel", str, None),
    ],
    
    "misc": [
        ("printtags_cmd", str, "./printtags.py"),
        ("tagmanip26_cmd", str, os.path.abspath(os.path.join(os.path.split(os.path.split(__file__)[0])[0],"tagmanip26.py"))), # assume tagmanip26.py lives in the same directory as this module
        ("show_ids", bool, False),
    ]
}
options = Config()
def init():
    options.readFromFile(constants.CONFIG)