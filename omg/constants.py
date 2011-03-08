# -*- coding: utf-8 -*-
import os
import logging

HOME    = os.path.expanduser("~")
CONFDIR = os.path.join(HOME, ".omg")
CONFIG  = os.path.join(CONFDIR, "config")
SHELVE = os.path.join(CONFDIR,"shelve","shelve")
IMAGES = "images/"

LOGLEVELS = {'debug': logging.DEBUG,
             'info': logging.INFO,
             'warning':logging.WARNING,
             'error':logging.ERROR,
             'critical':logging.CRITICAL
             }

YES_ANSWERS = ["y", "Y", ""]

FILL_CHARACTERS = "-–—•.,:;/ "

VERSION = '0.1alpha'

# Maximum length of encoded(!) tag-values of type varchar and the length of the MySQL-columns to hold them.
TAG_VARCHAR_LENGTH = 255

# Separators which may separate different values in tags (usually you'll want to split the tag into one tag for each value)
SEPARATORS = ('/', " / ", ' - ', ", ")
