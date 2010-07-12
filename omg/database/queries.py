# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

"""This module encapsulate common SQL queries in inside handy function calls."""


import omg
import omg.database
import omg.database.sql

def idFromFilename(filename):
    """Retrieves the container_id of a file from the given path, or None if it is not found."""
    try:
        return omg.database.get().query("SELECT container_id FROM files WHERE path=?;", filename).getSingle()
    except omg.database.sql.DBException:
        return None