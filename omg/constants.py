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

TAG_VARCHAR_LENGTH = 255