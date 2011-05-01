# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer, Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

"""
This module stores the default configuration of OMG' core. Plugin default configuration is returned by the plugin's defaultConfig and defaultStorage methods. The return values of these methods use the same format as the dicts in this module:

defaults and defaultStorage are dicts mapping section names to other dicts which store the options and nested sections of that section (using their names as keys again). Nested sections are again dicts, of course. Options are tuples consisting of:

    - For default: type (one of str,list or int),default value and optionally a description string.
    - For defaultStorage: default value and optionally a description string. If you don't specify a description you must use tuples with only one element!

"""

from PyQt4 import QtCore

# No use to translate strings here, as this is executed before any translators have been loaded.
defaults = {
"main": {
    "collection": (str,".","Music collection base directory"),
    "plugins": (list,["dbanalyzer","logodock"],"List of plugin names (i.e. the name of the corresponding directory in /omg/plugins/.")
},
    
"i18n": {
    "locale": (str,QtCore.QLocale.system().name(), "The locale used by OMG (e.g. de_DE)."),
},

"database": {
    "drivers": (list,["qtsql"], "List of drivers OMG will try to connect to the database."),
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
},

"mpd": {
    "timer_interval": (int,300,"Interval of mpd synchronization"),
    "host": (str,"localhost","MPD's host name"),
    "port": (int,6600,"MPD's port"),
},

"tags": {
    "tag_order": (list,["title","artist","album","composer","date","genre","peformer","conductor"],
                  "Order in which tags will be displayed. Must contain title and album! Tags which don't appear in this list will be displayed in arbitrary order after the tags in the list."),
    "title_tag": (str,"title","Key of the title-tag."),
    "album_tag": (str,"album","Key of the album-tag.")
},

"gui": {
    "browser_cover_size": (int,40,"Size of covers in the browser."),
    "small_cover_size": (int,40,"Small cover size used in various places."),
    "large_cover_size": (int,60,"Not so small cover size used in various places."),
    "detail_cover_size": (int,160,"Cover size in details view."),
    "iconsize": (int,16,"Size of various icons."),
    "max_browser_views": (int,5,"The maximal number of views the browser will allow."),
    "mime": (str,"application/x-omgelementlist","Mime-type used to copy and paste data within OMG."),
    "startTab": (str,"playlist","Either 'playlist' or 'editor' whatever you want to see on startup."),
},

"misc": {
    "show_ids": (bool,False,"Whether OMG should display element IDs"),
    "consoleLogLevel": (str,"",
                        "Log-messages of this loglevel and higher are additionally printed to stderr. Leave it empty to use the configuration specified in logging.conf.")
}
}

# The default values must be stored in tuples of length 1, since dicts will start a new section
storage = {
"gui": {
    'central_widgets': ([],),
    'dock_widgets': ([],),
}
}

# Stuff from OMG 0.1 --- not clear whether it will be used in OMG 0.2
   # 'browser_views': ([[['composer','artist','performer']],[['genre'],['composer','artist','performer']]],),
    #~ options.addOption("tags",       "search_tags",      list,   ["album",
                                                                 #~ "performer",
                                                                 #~ "conductor",
                                                                 #~ "title",
                                                                 #~ "lyricist",
                                                                 #~ "composer",
                                                                 #~ "date",
                                                                 #~ "artist"]      , description="Tags that will be searched, if you type a text without prefix in a searchbox. Use prefixes to search for other tags.")
    #~ options.addOption("tags",       "ignored_tags",     list,   ["tracktotal",
                                                                 #~ "disctotal",
                                                                 #~ "tracknumber",
                                                                 #~ "discnumber"]  )
