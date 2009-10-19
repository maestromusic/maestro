# -*- coding: utf-8 -*-
import os
import logging

HOME    = os.path.expanduser("~")
CONFDIR = os.path.join(HOME, ".omg")
CONFIG  = os.path.join(CONFDIR, "config")

LOGLEVELS = {'debug': logging.DEBUG,
             'info': logging.INFO,
             'warning':logging.WARNING,
             'error':logging.ERROR,
             'critical':logging.CRITICAL
             }

YES_ANSWERS = ["y", "Y", ""]
