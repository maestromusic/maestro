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

import os

VERSION = '0.3.0' # major, minor, revision

HOME    = os.path.expanduser("~")

YES_ANSWERS = ["y", "Y", ""]

# Type of a change
ADDED,CHANGED,DELETED = 1,2,3
# Use remove if an item is removed from a list, selection etc., but does still exist.
# Use delete if an item is completely deleted
# (even if it can be restored via undo. If the user wants to get rid of it, use delete)
REMOVED = DELETED
CHANGE_TYPES = (ADDED,CHANGED,DELETED)

# Command types
ADD, CHANGE, DELETE = 1,2,3
REMOVE = DELETE
COMMAND_TYPES = CHANGE_TYPES


def compareVersion(v):
    """Returns 1 if the program version is larger than v, 0 if it is equal, and -1 if it is lower."""
    myVersion =  tuple(map(int, VERSION.split('.')))
    otherVersion = tuple(map(int, v.split('.')))
    if myVersion > otherVersion:
        return 1
    elif myVersion == otherVersion:
        return 0
    else:
        return -1
    
# Maximum length of encoded(!) tag-values of type varchar and the length of the MySQL-columns to hold them.
TAG_VARCHAR_LENGTH = 255

# Maximum length of encoded(!) flag-names.
FLAG_VARCHAR_LENGTH = 63

# Separators which may separate different values in tags
# (usually you'll want to split the tag into one tag for each value)
SEPARATORS = ('/', " / ", ' - ', ", ", ' & ')
