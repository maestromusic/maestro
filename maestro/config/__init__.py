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
This package handles Maestro's configuration. There are five sources where configuration may come from:
Three files in the configuration directory, the default options which are hard coded into this module
(and into plugins) and finally the command line where arbitrary config options may be overwritten using
the -c option.
The three files are:

    * 'config'. This is the main configuration file and the one that is mainly edited by the user.
      But it may be written from the program, too. It contains several sections which may contain options
      and nested sections. Options must have a type (str, int, bool or list) and a default value stored in
      defaultconfig. To get the option 'size' from the section 'gui' simply use:
    
        config.options.gui.size
      
      This will directly return the option's value.
      
      Instead of attribute access you may also use item access::
      
          config.options['gui']['size']
        
      Both types of access allow to write values via assignment.
      Note that values will not be written to the file before the application terminates, though.

    * 'storage'. This file also holds persistent information but is mainly written by the program. It uses
      JSON notation, so it can store any combination of Python's standard types including lists and dicts.
      The file is human readable and can be edited by the user (less comfortable than config).
      Access works like for config, but with the variable 'config.storage'.

    * 'binary'. Like 'storage' but stored in a binary file using pickle.

All files can only contain options which are defined in the corresponding dicts in this module or in the
configuration of a plugin that is returned by the methods 'defaultConfig', 'defaultStorage' or
'defaultBinary' within the module. (To be precise the first level of each file may contain
sections which are not defined. Maestro will assume that they belong to a plugin that is not loaded).

Call 'init' at application start to read options and call 'shutdown' at the end to write the
options. Use 'loadPlugins' and 'removePlugins' to add or remove plugin configuration.
"""

import functools

from .config import *
from .. import logging, VERSION

# Directory of the configuration files.
CONFDIR = None

# These are the access objects.
options = None
storage = None
binary = None


def init(cmdConfig=[], testMode=False):
    """Initialize the config-module: Read the config files and create the module variables. *cmdConfig* is a
    list of options given on the command line that will overwrite the corresponding option from the file or
    the default. Each list item has to be a string like 'database.type=sqlite'.
    If *testMode* is True, a different file will be used for config options (testconfig instead of config),
    storage will be set to the default values and binary will be empty.
    """
    
    # Find the config directory and ensure that it exists
    global CONFDIR
    CONFDIR = defaultConfigDirectory('maestro')
    fileData = [('options', 'config', 'config' if not testMode else 'testconfig', 'configOptions'),
                ('storage', 'json',   'storage' if not testMode else None, 'storageOptions'),
                ('binary',  'pickle', 'binary' if not testMode else None, 'binaryOptions')
                ]

    for name, type, fileName, defaults in fileData:
        file = addFile(type, os.path.join(CONFDIR, fileName), globals()[defaults],
                       allowUndefinedSections=True, version=VERSION,
                       errorMethod=functools.partial(logging.error, __name__))
        globals()[name] = file.getAccess()
        del globals()[defaults] # not necessary anymore
    
    # Set values from command line
    for line in cmdConfig:
        try:
            option, value = (s.strip() for s in line.split('=', 2))
            getFile(options).setTemporaryValue(option, value)
        except KeyError:
            logging.error(__name__, "Unknown config option on command line '{}'.".format(line))
        except:
            logging.error(__name__, "Invalid config option on command line '{}'.".format(line))
  
  
def shutdown():
    """Store the configuration persistently on application shutdown."""
    for file in [options, storage, binary]:
        file = getFile(file)
        try:
            file.write()
        except ConfigError as e:
            logging.error(__name__, str(e))
    

# No use to translate strings here, as this is executed before any translators have been loaded.
configOptions = collections.OrderedDict((
("main", {
    "plugins": (list, [], "List of plugin names (i.e. the name of the corresponding directory in /maestro/plugins/."),
    "music_extensions": (list, ["flac", "m4a", "mp3", "mp4", "mpc", "oga", "ogg", "spx", "wma"], "music file extensions")
}),
    
("i18n", {
    # An empty locale will start the install tool
    "locale": (str, '', "The locale used by Maestro (e.g. de_DE)."),
}),

("database", {
    "type": (str, "sqlite", 'Database type, usually "sqlite" or "mysql".'),
    "driver": (str, '', "(Optional) database driver to use, e.g. 'mysqldb', 'mysqlconnector'."),
    "name": (str, "maestro", "Name of the database"),
    "user": (str, "", "User name"),
    "password": (str, "", "Password"),
    "host": (str, "localhost", "Host name of the database server"),
    "port": (int, 0, "Port of the database server"),    
    "sqlite_path": (str, "config:maestro.db", "Path to the SQLite database. May start with 'config:' indicating that the path is relative to the configuration directory."),
    "prefix":  (str, "", "Prefix which will be prepended to the table names."),
}),

("tags", {
    "title_tag": (str, "title", "Key of the title-tag."),
    "album_tag": (str, "album", "Key of the album-tag."),
    "search_tags": (list, ["album", "performer", "conductor", "title", "lyricist", "composer", "date", "artist"],
                    "Tags that will be searched, if you type a text without prefix in a searchbox. Use prefixes to search for other tags."),
    "auto_delete": (list, [], "list of tags that will be removed from files when they are imported into the editor"),
    "auto_replace": (str, '', "list of of tag pairs. When files are imported to the editor, tags are replaced according to these pairs. Each list entry must be of the form '(albumartist,performer)'.")
}),

("gui", {
    "mime": (str, "application/x-maestroelementlist", "Mime-type used to copy and paste data within Maestro."),
    "iconsize": (int, 16, "Size of various icons."),
    "flageditor": {
                "animation": (bool, True, "Enable/disable animations in the flageditor."),
                "max_tooltip_lines": (int, 5, "Maximum number of lines that will be shown in a tooltip (containing element titles) in the flageditor.")
    },
    "browser": {
                "max_view_count": (int, 5, "The maximal number of views the browser will allow."),
    }
}),
("filesystem", {
    "scan_interval": (int, 1800, "Interval (in seconds) in which the filesystem will be rescanned for changes"),
    "acoustid_apikey": (str, "VGPeEVtB", "API key for AcoustID web service"),
}),
("misc", {
    "show_ids": (bool, False, "Whether Maestro should display element IDs"),
    "cover_path": (str, "covers", "Path where Maestro stores and caches covers. Relative paths are interpreted as relative to the config directory."),
    "cover_extension": (str, "png", "Extension that is used to save covers. Must be supported by Qt. Note that Last.fm, which is where covers are downloaded by default, uses png's."),
    "consoleLogLevel": (str, "",
                        "Log-messages of this loglevel and higher are additionally printed to stderr. Leave it empty to use the configuration specified in the logging configuration (storage.options.main.logging)."),
    "debug_events": (bool, False, "Whether to print a debug message for each change event.")
}),
))


# Remember that values of types tuple or dict must be enclosed in a tuple
storageOptions = collections.OrderedDict((
("main", {
    # Configuration for logging.config.dictConfig.
    # Confer http://docs.python.org/py3k/library/logging.config.html#logging-config-dictschema
    # To change logging temporarily, copy this into your storage file and change it.
    'logging': ({
        "version": 1,
        "formatters": {
            "formatter": {"format": "%(asctime)s: %(levelname)s - %(message)s"},
        },
        "handlers": {
            "consoleHandler": {
                "class": "logging.StreamHandler",
                "level": "DEBUG",
                "formatter": "formatter",
                "stream": "ext://sys.stdout",
            },
            "fileHandler": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "DEBUG",
                "formatter": "formatter",
                "filename": os.path.join(os.path.expanduser("~"), ".config", "maestro", "maestro.log"),
                "mode": 'a',
                "maxBytes": 2000,
                "backupCount": 2
            }
        },
        "root": {
            "level": "DEBUG",
            "handlers": ["consoleHandler", "fileHandler"]
        }
      },),
}),
("editor", {
    'format_string' : "%{artist}/%{date} - %{album}/%{tracknumber} - %{title}.%{*}",
    'albumguesser_profiles': [],
}),
("gui", {
    'perspectives': ({},),
    'delegates': [],
    'layoutFrozen': False,
    'merge_dialog_container_type': None,
    'tag_editor_include_contents': True,
}),
("player", {
    'profiles': [],
}),
("filesystem", {
    'sources': [],
}),
("misc", {
    'last_cover_check': 0,
}),
))

binaryOptions = {
"gui": {
    "mainwindow_geometry": None,
    "mainwindow_maximized": False,
    "mainwindow_state": None,
    "preferences_geometry": None,
}
}