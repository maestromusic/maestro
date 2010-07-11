# -*- coding: utf-8 -*-
# Copyright 2009 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from configparser import RawConfigParser
import logging
import os.path
import shelve as shelveModule

from omg import constants

_config = RawConfigParser()
get = _config.get
set = _config.set

def init(*config_files):
    """Set default options and overwrite them with the options in the given config files."""
    default_options = {
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
            # Tags which will be indexed in their own database tables. Indexed tags have a type which defaults to varchar and may be specified in parentheses after the tagname (e.g. date(date)).
            "indexed_tags":"album,artist,composer,date(date),genre,performer,title",
            # Tags which will be totally ignored by this application.
            "ignored_tags":"encodedby,tracktotal,disctotal,tracknumber,discnumber",
            
            # Names of the tags which have a special meaning for the application and cannot always be treated generically.
            # This allows to use other strings for the title-tag for example.
            "title_tag": "title",
            "album_tag": "album",
            "date_tag": "date",
        },
        
        "browser": {
            "tag_sets": "[[composer,artist,performer]],[[genre],[composer,artist,performer]],"
                       +"[[genre]],[[artist]],[[composer]],[[performer]]"
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
            
            # Order in which tags will be displayed. Must contain title and album! Tags which don't appear in this list will be displayed in arbitrary order after the tags in the list.
            "tag_order": "title,album,composer,artist,performer,conductor,date,genre"
        },
        
        "misc": {
            "printtags_cmd":"./printtags.py",
            "tagmanip26_cmd":os.path.abspath(os.path.join(os.path.split(os.path.split(__file__)[0])[0],"tagmanip26.py")), # assume tagmanip26.py lives in the same directory as this module
            "loglevel":"warning",
            "show_ids":0,
        }
    }
    
    for section, configs in default_options.items():
        if not _config.has_section(section):
            _config.add_section(section)
        for key, value in configs.items():
            _config.set(section, key, value)
    
    _config.read(config_files)
    logging.basicConfig(level=constants.LOGLEVELS[get("misc","loglevel")], format='%(levelname)s: in Module %(name)s: %(message)s')

init(constants.CONFIG)


shelve = shelveModule.open(constants.SHELVE)

def initShelve(shelve):
    """If the shelve does not contain a value for an option, store the default value."""
    defaultOptions = {
        'widget_position': None, # center the window
        'widget_width': 800,
        'widget_height': 600,
        
        'browser_views': [[['composer','artist','performer']],[['genre'],['composer','artist','performer']]],
    }
    for key,option in defaultOptions.items():
        if key not in shelve:
            shelve[key] = option    

initShelve(shelve)