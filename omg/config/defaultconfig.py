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
This module stores the default configuration of OMG' core. Plugin default configuration is returned by the
plugin's ``defaultConfig`` and ``defaultStorage`` methods. The return values of these methods use the same
format as the corresponding dicts in this module.

``defaults`` is a dict mapping section names to other dicts which store the options and nested sections of
that section. Options are tuples consisting of: type (one of str,list or int), default value and optionally 
a description string. Nested sections are again dicts, of course.

``defaultStorage`` works similar, but options are simply stored as values (no tuple necessary as there is no
type and description). To distinguish dicts which are nested sections from dicts which are values, section
names must be prepended with 'SECTION:' (this is not part of the section name).
"""

import os
from collections import OrderedDict


# No use to translate strings here, as this is executed before any translators have been loaded.
defaults = OrderedDict((
("main", {
    "collection": (str,"","Music collection base directory"),
    "plugins": (list,[],"List of plugin names (i.e. the name of the corresponding directory in /omg/plugins/."),
    "extensions": (list, ["flac", "m4a", "mp3", "mp4", "mpc", "oga", "ogg", "spx"], "file extensions")
}),
    
("i18n", {
    # An empty locale will start the install tool
    "locale": (str,'', "The locale used by OMG (e.g. de_DE)."),
}),

("database",{
    "type": (str,"mysql",'Either "mysql" or "sqlite".'),
    "prefix":  (str,"","Prefix which will be prepended to the table names."),
    
    "mysql_drivers": (list,["qtsql"], "List of drivers OMG will use to try to connect to a MySQL database."),
    "mysql_db": (str,"omg","Name of the database"),
    "mysql_user": (str,"","MySQL user name"),
    "mysql_password": (str,"","MySQL password"),
    "mysql_host": (str,"localhost","MySQL host name"),
    "mysql_port": (int,3306,"MySQL port"),
    
    "sqlite_path": (str,"config:omg.db","Path to the SQLite database. May start with 'config:' indicating that the path is relative to the configuration directory.")
}),

("mpd", {
    "timer_interval": (int,300,"Interval of mpd synchronization"),
    "host": (str,"localhost","MPD's host name"),
    "port": (int,6600,"MPD's port"),
}),

("tags", {    
    "title_tag": (str,"title","Key of the title-tag."),
    "album_tag": (str,"album","Key of the album-tag."),
    "search_tags":(list,["album","performer","conductor","title","lyricist","composer","date","artist"],
                    "Tags that will be searched, if you type a text without prefix in a searchbox. Use prefixes to search for other tags."),
    "always_delete": (list, [], "Tags which will be deleted from all files in which they occur.")
}),

("gui", {
    "mime": (str,"application/x-omgelementlist","Mime-type used to copy and paste data within OMG."),
    "iconsize": (int,16,"Size of various icons."),
    "flageditor": {
                "animation": (bool,True,"Enable/disable animations in the flageditor."),
                "max_tooltip_lines": (int,5,"Maximum number of lines that will be shown in a tooltip (containing element titles) in the flageditor.")
    },
    "browser": {
                "max_view_count": (int,5,"The maximal number of views the browser will allow."),
    }
}),
("filesystem", {
    "scan_interval": (int,120,"Interval (in seconds) in which the filesystem will be rescanned for changes"),
    "dump_method": (str,"ffmpeg", "Method used to dump raw audio data from files for hashing"),
    "disable":(bool,False,"completely disable filesystem synchronization"),
}),
("misc", {
    "show_ids": (bool,False,"Whether OMG should display element IDs"),
    "cover_path": (str,"covers","Path where OMG stores and caches covers. Relative paths are interpreted as relative to the config directory."),
    "cover_extension": (str,"png","Extension that is used to save covers. Must be supported by Qt. Note that Last.fm, which is where covers are downloaded by default, uses png's."),
    "consoleLogLevel": (str,"",
                        "Log-messages of this loglevel and higher are additionally printed to stderr. Leave it empty to use the configuration specified in the logging configuration (storage.options.main.logging)."),
    "debug_events": (bool,False,"Whether to print a debug message for each change event.")
}),
))


# To distinguish sections from values of type dict,
# mark sections with 'SECTION:' (this is not part of the section name).
storage = OrderedDict((
("SECTION:main", {
    # Configuration for logging.config.dictConfig.
    # Confer http://docs.python.org/py3k/library/logging.config.html#logging-config-dictschema
    # To change logging temporarily, copy this into your storage file and change it.
    'logging': {
        "version": 1,
        "formatters": {
            "consoleFormatter": {"format": "%(asctime)s: %(levelname)s - %(name)s - %(message)s"},
            "fileFormatter": {"format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s}"},
        },
        "handlers": {
            "consoleHandler": {
                "class": "logging.StreamHandler",
                "level": "DEBUG",
                "formatter": "consoleFormatter",
                "stream": "ext://sys.stdout",
            },
            "fileHandler": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "DEBUG",
                "formatter": "fileFormatter",
                "filename": os.path.join(os.path.expanduser("~"),".config", "omg","omg.log"),
                "mode": 'a',
                "maxBytes": 2000,
                "backupCount": 2
            }
        },
        "root": {
            "level": "DEBUG",
            "handlers": ["consoleHandler","fileHandler"]
        }
      },
}),
("SECTION:editor", {
    'format_string' : "%{artist}/%{date} - %{album}/%{tracknumber} - %{title}.%{*}",
    'albumguesser' : {"profiles" : [] },
}),
("SECTION:gui", {
    'central_widgets': [],
    'dock_widgets': [],
    'central_tab_index': -1,
    # List of all delegate configurations. Built-in configurations will be added regardless of this list.
    'delegate_configurations': [],
}),
("SECTION:browser", {
    'views': [[['composer','artist','performer']],[['genre'],['composer','artist','performer']]],
}),
("SECTION:player", {
    'profiles': [],
}),
("SECTION:misc", {
    'last_cover_check': 0
})
))
