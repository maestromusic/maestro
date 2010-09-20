#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-
# Copyright 2009 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from omg import database, constants, config
import os
import pickle
import datetime
import logging

def relPath(file):
    """Returns the relative path of a music file against the collection base path."""
    return os.path.relpath(file,config.get("music","collection"))

def absPath(file):
    """Returns the absolute path of a music file inside the collection directory, if it is not absolute already."""
    if not os.path.isabs(file):
        return os.path.join(config.get("music","collection"),file)
    else:
        return file

def getIcon(name):
    return os.path.join(constants.IMAGES, "icons", name)


class FlexiDate:
    
    def __init__(self, year, month = None, day = None):
        self.year = year
        if month == 0:
            self.month = None
        else:
            self.month = month
        if day == 0:
            self.day = None
        else:
            self.day = day
    
    @staticmethod
    def strptime(string):
        return FlexiDate(*map(int,string.split("-")))
    
    def strftime(self, format = ["{Y:04d}-{m:02d}-{d:02d}", "{Y:04d}-{m:02d}", "{Y:04d}"]):
        if self.month:
            if self.day:
                format = format[0]
            else:
                format = format[1]
        else:
            format = format[2]
        return format.format(Y=self.year, m=self.month, d=self.day)
    
    def __str__(self):
        return self.strftime()
        