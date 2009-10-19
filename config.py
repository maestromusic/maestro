# -*- coding: utf-8 -*-
# Copyright 2009 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

import constants
from configparser import RawConfigParser
import logging

_config = RawConfigParser()
get = _config.get
set = _config.set

def init(*config_files):
    """Sets default options and overwrites them with the options in the given config files."""
    default_options = {
        "database": {
            "mysql_host":"localhost",
            "mysql_port":"3306",
            "mysql_user":"",
            "mysql_password":"",
            "mysql_db":"omg",
        },
        
        "tags": {
            "indexed_tags":"album,artist,title,composer,performer,genre,date(date)",
            "ignored_tags":"encodedby,tracktotal,disctotal,tracknumber,discnumber",
        },
        
        "misc": {
            "printtags_cmd":"printtags.py",
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
