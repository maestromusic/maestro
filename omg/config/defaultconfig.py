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
This module stores the default configuration of OMG' core. Plugin default configuration is returned by the
plugin's ``defaultConfig`` and ``defaultStorage`` methods. The return values of these methods use the same
format as the dicts in this module:

``defaults`` and ``defaultStorage`` are dicts mapping section names to other dicts which store the options
and nested sections of that section (using their names as keys again). Nested sections are again dicts, of
course.
Options are tuples consisting of:

    * For ``default``: type (one of str,list or int),default value and optionally a description string.
    * For ``defaultStorage``: default value and optionally a description string. If you don't specify a
      description, you must use tuples with only one element!

"""

import os, logging, sys

from PyQt4 import QtCore
from collections import OrderedDict

# No use to translate strings here, as this is executed before any translators have been loaded.
defaults = OrderedDict((
("main", {
    "collection": (str,".","Music collection base directory"),
    "plugins": (list,["dbanalyzer","logodock"],"List of plugin names (i.e. the name of the corresponding directory in /omg/plugins/."),
    "extensions": (list, ["flac", "m4a", "mp3", "mp4", "mpc", "oga", "ogg", "spx"], "file extensions")
}),
    
("i18n", {
    "locale": (str,QtCore.QLocale.system().name(), "The locale used by OMG (e.g. de_DE)."),
}),

("database",{
    "drivers": (list,["qtsql"], "List of drivers OMG will use to try to connect to the database."),
    "prefix":  (str,"","Prefix which will be prepended to the table names."),
    "mysql_db": (str,"omg","Name of the database"),
    "mysql_user": (str,"","MySQL user name"),
    "mysql_password": (str,"","MySQL password"),
    "mysql_host": (str,"localhost","MySQL host name"),
    "mysql_port": (int,3306,"MySQL port"),
    
    "test_db": (str,"","Name of the database used by (unit)test scripts. If this is empty the normal database will be used (In this case you must specify a test-prefix which differs from the standard prefix."),
    "test_user": (str,"","MySQL user name for test scripts"),
    "test_password": (str,"","MySQL password for test scripts"),
    "test_host": (str,"localhost","MySQL host name for test scripts"),
    "test_port": (int,3306,"MySQL port for test scripts"),
    "test_prefix": (str,"omgtest_","Table prefix for the test tables."),
}),

("mpd", {
    "timer_interval": (int,300,"Interval of mpd synchronization"),
    "host": (str,"localhost","MPD's host name"),
    "port": (int,6600,"MPD's port"),
}),

("tags", {
    "tag_order": (list,["title","artist","album","composer","date","genre","peformer","conductor"],
                  "Order in which tags will be displayed. Must contain title and album! Tags which don't appear in this list will be displayed in arbitrary order after the tags in the list."),
    "title_tag": (str,"title","Key of the title-tag."),
    "album_tag": (str,"album","Key of the album-tag."),
    "search_tags":(list,["album","performer","conductor","title","lyricist","composer","date","artist"],
                    "Tags that will be searched, if you type a text without prefix in a searchbox. Use prefixes to search for other tags."),
    "always_delete": (list, ["a_tag_nobody_would_want_in_his_files"], "Tags which will be deleted from all files in which they occur.")
}),

("gui", {
    "mime": (str,"application/x-omgelementlist","Mime-type used to copy and paste data within OMG."),
    "iconsize": (int,16,"Size of various icons."),
    "editor": {
                "cover_size": (int,64,"Size of covers in the editor."),
                "left_tags": (list,['composer','artist','performer'],"Tags in the left column."),
                "right_tags": (list,['date','conductor'],"Tags in the right column."),
    },
    "flageditor": {
                "animation": (bool,True,"Enable/disable animations in the flageditor."),
                "max_tooltip_lines": (int,5,"Maximum number of lines that will be shown in a tooltip (containing element titles) in the flageditor.")
    },
    "browser": {
                "cover_size": (int,40,"Size of covers in the browser."),
                "left_tags": (list,['composer','artist','performer'],"Tags in the left column."),
                "right_tags": (list,['conductor'],"Tags in the right column."),
                "show_sort_values": (bool,False,"Whether the browser should display sortvalues instead of real values (if present)."),
                "max_view_count": (int,5,"The maximal number of views the browser will allow."),
                "show_positions": (bool,True,"Whether to display positions in the browser."),
    },
    # TODO: Remove these options when the new delegates are used everywhere 
    "browser_cover_size": (int,40,"Size of covers in the browser."),
    "small_cover_size": (int,40,"Small cover size used in various places."),
    "large_cover_size": (int,60,"Not so small cover size used in various places."),
    "detail_cover_size": (int,160,"Cover size in details view."),
}),

("misc", {
    "show_ids": (bool,False,"Whether OMG should display element IDs"),
    "consoleLogLevel": (str,"",
                        "Log-messages of this loglevel and higher are additionally printed to stderr. Leave it empty to use the configuration specified in the logging configuration (storage.options.main.logging).")
})
))

# The default values must be stored in tuples of length 1, since dicts will start a new section
storage = OrderedDict((
("main", {
    # Configuration for logging.config.dictConfig.
    # Confer http://docs.python.org/py3k/library/logging.config.html#logging-config-dictschema
    # To change logging temporarily, copy this into your storage file and change it.
    'logging': ({
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
    ),
}),
("editor", {
    'format_string' : ("%{artist}/%{date} - %{album}/%{tracknumber} - %{title}.%{*}",),
    'guess_profiles' : ({"default" : ["album", "DIRECTORY"]},),
}),
("gui", {
    'central_widgets': ([],),
    'dock_widgets': ([],),
    'central_tab_index': (-1,),
}),
("browser", {
    'views': ([[['composer','artist','performer']],[['genre'],['composer','artist','performer']]],),
}),

))
