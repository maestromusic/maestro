# -*- coding: utf-8 -*-
import os
import logging

HOME    = os.path.expanduser("~")
IMAGES = "images"


YES_ANSWERS = ["y", "Y", ""]

FILL_CHARACTERS = "-–—•.,:;/ "

VERSION = '0.2alpha'

# Maximum length of encoded(!) tag-values of type varchar and the length of the MySQL-columns to hold them.
TAG_VARCHAR_LENGTH = 255

# Maximum length of encoded(!) flag-names.
FLAG_VARCHAR_LENGTH = 63

# Separators which may separate different values in tags (usually you'll want to split the tag into one tag for each value)
SEPARATORS = ('/', " / ", ' - ', ", ")
