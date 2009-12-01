#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
# Convenience script to reset the database (drop all tables and create them again) and fill the tagids-table according to the indexed_tags-option of the config-file.
#
from omg import database

if input("Really? (y,n)") != "y":
    quit()

database.connect()
print("Resetting database...")
database.resetDatabase()
database.checkTagIds(True)
print("...done")