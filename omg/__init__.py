#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-
# Copyright 2009 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from omg import constants
from omg.config import options
import os
import pickle
import datetime
import logging

def relPath(file):
    """Returns the relative path of a music file against the collection base path."""
    if os.path.isabs(file):
        return os.path.relpath(file, options.music.collection)
    else:
        return file

def absPath(file):
    """Returns the absolute path of a music file inside the collection directory, if it is not absolute already."""
    if not os.path.isabs(file):
        return os.path.join(options.music.collection, file)
    else:
        return file

def getIcon(name):
    return os.path.join(constants.IMAGES, "icons", name)


class FlexiDate:
    """A FlexiDate is a date which may be only a year, or a year and a month, or a year+month+day."""
     
    def __init__(self, year, month = None, day = None):
        """For unspecified month or day, you may pass None or 0, which will be converted to None."""
        self.year = int(year)
        if month == 0 or month is None: # cannot pass None to int(), so we have to check for it here
            self.month = None
        else:
            self.month = int(month)
        if day == 0 or day is None:
            self.day = None
        else:
            self.day = int(day)
    
    @staticmethod
    def strptime(string):
        """Parse FlexiDates from Strings like YYYY-mm-dd or YYYY-mm or YYYY."""
        if not isinstance(string,str):
            raise TypeError("Argument must be a string.")
        try:
            return FlexiDate(*map(int,string.split("-")))
        except TypeError as e:
            # A TypeError is raised if the number of arguments doesn't fit. In our case that's more a kind of ValueError.
            raise ValueError(e.message)
    
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

    def __repr__(self):
        if self.month:
            if self.day:
                return "FlexiDate({},{},{})".format(self.year,self.month,self.day)
            else: return "FlexiDate({},{})".format(self.year,self.month)
        else: return "FlexiDate({})".format(self.year)
        
    def __lt__(self, other):
        if self.year < other.year:
            return True
        elif self.year > other.year:
            return False
        elif self.month == None:
            return other.month != None
        else: # self.month != None, year equals
            if other.month == None:
                return False
            elif self.month < other.month:
                return True
            elif self.month > other.month:
                return False
            else:
                if self.day == None:
                    return other.day != None
                else:
                    if other.day == None:
                        return False
                    else:
                        return self.day < other.day
    def __gt__(self, other):
        return other.__lt__(self)
    
    def __le__(self, other):
        return self == other or self.__lt__(other)
    
    def __ge__(self, other):
        return self == other or self.__gt__(other)
        
    def __eq__(self, other):
        return isinstance(other,FlexiDate) and\
            self.year == other.year and self.month == other.month and self.day == other.day
        
    def __ne__(self,other):
        return not isinstance(other,FlexiDate) or\
            self.year != other.year or self.month != other.month or self.day != other.day
