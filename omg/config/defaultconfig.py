# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer, Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtCore

# No use to translate strings here, as this is executed before any translators have been loaded.
defaults = {
"main": {
    "collection": (str,".","Music collection base directory"),
    "plugins": (list,["dbanalyzer"],"List of plugin names (i.e. the name of the corresponding directory in /omg/plugins/.")
},
    
"i18n": {
    "locale": (str,QtCore.QLocale.system().name(), "The locale used by OMG (e.g. de_DE)."),
},

"database": {
    "drivers": (list,["qtsql"], "List of drivers OMG will try to connect to the database."),
    "prefix":  (str,"","Prefix which will be prepended to the table names."),
    "mysql_user": (str,"","MySQL user name"),
    "mysql_password": (str,"","MySQL password"),
    "mysql_host": (str,"localhost","MySQL host name"),
    "mysql_port": (int,3306,"MySQL port"),
    "mysql_db": (str,"omg","Name of the database"),
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

storage = {
"gui": {
    'widget_position': (None,), # center the window
    'widget_width': (800,),
    'widget_height': (600,),
    'browser_views': ([[['composer','artist','performer']],[['genre'],['composer','artist','performer']]],),
}
}

# Stuff from OMG 0.1 --- not clear whether it will be used in OMG 0.2
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
