# -*- coding: utf-8 -*-
# Copyright 2009 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

import constants
from configparser import RawConfigParser

_config = RawConfigParser()
get = _config.get
set = _config.set

def init(*config_files):
    default_options = {
        "database": {
            "mysql_host":"localhost",
            "mysql_port":"3306",
            "mysql_user":"",
            "mysql_password":"",
            "mysql_db":"omg"
        },
        
        "tags": {
            "indexed_tags":"album,artist,title,composer,performer,genre,date",
            "ignored_tags":"encodedby"
        }
    }
    
    for section, configs in default_options.items():
        _config.add_section(section)
        for key, value in configs.items():
            _config.set(section, key, value)
    
    _config.read(config_files)