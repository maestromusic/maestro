# -*- coding: utf-8 -*-
import os
import logging

HOME    = os.path.expanduser("~")
IMAGES = "images"


YES_ANSWERS = ["y", "Y", ""]

REAL, EDITOR = range(1,3) # Levels for commands and events
DISK, DB, CONTENTS = range(3) # modes for removing elements

#VERSION = '0.2alpha'
VERSION = '0.2.1' # major, minor, revision
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

# Separators which may separate different values in tags (usually you'll want to split the tag into one tag for each value)
SEPARATORS = ('/', " / ", ' - ', ", ")
