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
    """A FlexiDate is a date which may be only a year, or a year and a month, or a year+month+day."""
     
    def __init__(self, year, month = None, day = None):
        """For unspecified month or day, you may pass None or 0, which will be converted to None.""" 
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
        """Parse FlexiDates from Strings like YYYY-mm-dd or YYYY-mm or YYYY."""
        return FlexiDate(*map(int,string.split("-")))
    
    def strftime(self, format = ("{Y:04d}-{m:02d}-{d:02d}", "{Y:04d}-{m:02d}", "{Y:04d}")):
        """Format the FlexiDate according to the given format. Format must be a 3-tuple of
        format strings, where the first one if used if year, month and day are specified,
        the second one is used if only the day misses, and the third one is used if there
        is only a year. The format strings are python format strings, where Y=year, m=month, d=day."""
        if self.month:
            if self.day:
                format = format[0]
            else:
                format = format[1]
        else:
            format = format[2]
        return format.format(Y=self.year, m=self.month, d=self.day)
    
    def SQLformat(self):
        """Format the FlexiDate in a way that is suitable for MySQL."""
        return "{}-{}-{}".format(self.year, self.month or 0, self.day or 0)
    def __str__(self):
        return self.strftime()
    
    def __eq__(self, other):
        return self.year == other.year and self.month == other.month and self.day == other.day
        