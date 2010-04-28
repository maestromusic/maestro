# -*- coding: utf-8 -*-
# Copyright 2009 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from omg import constants
from configparser import RawConfigParser
import logging
import os.path

_config = RawConfigParser()
get = _config.get
set = _config.set

def init(*config_files):
    """Sets default options and overwrites them with the options in the given config files."""
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
            "timer_interval": "100"
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
            "artist_tag": "artist",
            "composer_tag": "composer",
            "performer_tag": "performer",
            "date_tag": "date",
            "genre_tag": "genre"
        },
        
        "browser": {
            "artist_tags": "composer,artist"
        },
        
        "misc": {
            "printtags_cmd":"./printtags.py",
            "tagmanip26_cmd":os.path.abspath(os.path.join(os.path.split(os.path.split(__file__)[0])[0],"tagmanip26.py")), # assume tagmanip26.py lives in the same directory as this module
            "loglevel":"warning",
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