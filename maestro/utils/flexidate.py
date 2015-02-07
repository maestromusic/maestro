# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2015 Martin Altmayer, Michael Helmling
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

import locale, re

from PyQt4 import QtCore
translate = QtCore.QCoreApplication.translate

from . import strings

class FlexiDate:
    """A FlexiDate is a date which can store a date consisting simply of a year or of a year and a month or
    of year, month and day. Maestro uses this class to store tags of type date, where most users will only
    specify a year, but some may give month and day, too.

    Note that while MySQL's DATE type can store dates where day and month may be unspecified, neither
    datetime.date nor QDate can. Thus binding FlexiDates to SQL-queries does not work. For this reason
    FlexiDates are stored as integers in the DB (confer FlexiDate.toSql and FlexiDate.fromSql).

    The parameters may be anything that can be converted to int. *month* and *day* may also be None.
    If *month* or *day* are 0 or None they are regarded as unspecified. Note that you must not
    give a nonzero *day* if *month* is zero or None. This method raises a ValueError if 
    conversion to int fails or if the date is invalid (confer datetime.date).
    """
    def __init__(self, year, month=None, day=None):
        self.year = int(year)
        
        if month == 0 or month is None: # cannot pass None to int(), so we have to check for it here
            self.month = None
            if day is not None and day != 0:
                raise ValueError("Cannot store a day if month is None.")
        elif 1 <= int(month) <= 12:
            self.month = int(month)
        else: raise ValueError("Invalid month given.")
        
        if day == 0 or day is None:
            self.day = None
        else:
            self.day = int(day)
            import datetime
            datetime.date(self.year, self.month, self.day) # Check date
    
    @staticmethod
    def _initFormat():
        """Initialize the class attributes FlexiDate._dateFormat and FlexiDate._dateOrder. These attributes
        depend on the locale and are used by strptime and strftime."""
        if not hasattr(FlexiDate, '_dateFormat'):
            format = locale.nl_langinfo(locale.D_FMT)
            match = re.match('%[dmY]([.\-/])%[dmY]([.\-/])%[dmY]', format)
            if match is not None:
                sep1, sep2 = match.group(1), match.group(2)
            else: sep1, sep2 = '//'
            FlexiDate._sep1, FlexiDate._sep2 = sep1, sep2
            if format.index('%d') < format.index('%m'):
                FlexiDate._dateFormat = ('{Y:04d}',
                                         '{m:02d}'+sep2+'{Y:04d}',
                                         '{d:02d}'+sep1+'{m:02d}'+sep2+'{Y:04d}')
                FlexiDate._dateOrder = (('year',), ('month','year'), ('day','month','year'))
            else:
                FlexiDate._dateFormat = ('{Y:04d}',
                                         '{m:02d}'+sep2+'{Y:04d}',
                                         '{m:02d}'+sep1+'{d:02d}'+sep2+'{Y:04d}')
                FlexiDate._dateOrder = (('year',), ('month','year'), ('month','day','year'))
    
    @staticmethod
    def getHumanReadableFormat():
        """Return a format string for the format used by FlexiDate that is easily readable.
        For example "mm/dd/YYYY"."""
        FlexiDate._initFormat()
        dateOrder = FlexiDate._dateOrder[2]
        tr = {'day': translate("FlexiDate", "dd"),
              'month': translate("FlexiDate", "mm"),
              'year': translate("FlexiDate", "YYYY")
        }
        return tr[dateOrder[0]] + FlexiDate._sep1 + tr[dateOrder[1]] + FlexiDate._sep2 + tr[dateOrder[2]]
        
    @staticmethod
    def strptime(string, crop=False, logCropping=True):
        """Parse FlexiDates from strings in a format depending on the locale. Raise a ValueError if that
        fails.
        If *crop* is True, the method is allowed to crop *string* to obtain a valid value. If *logCropping*
        is True, cropping will print a logger warning.
        """
        assert isinstance(string, str)
        
        # check for the default file format yyyy-mm-dd first
        # Chop of the time part of values of the form
        # YYYY-MM-DD HH:MM:SS
        # YYYY-MM-DD HH:MM
        # YYYY-MM-DD HH
        # These formats are allowed in the ID3 specification and used by Mutagen
        if crop and re.match("\d{4}-\d{2}-\d{2} \d{2}(:\d{2}){0,2}$", string) is not None:
            if logCropping:
                from .. import logging
                logging.getLogger(__name__).warning("dropping time of day in date string '{}'"
                                                    .format(string))
            string = string[:10]
            
        try:
            y,m,d = map(lambda v: None if v is None else int(v),
                        re.match("(\d{4})(?:-(\d{2})(?:\-(\d{2}))?)?", string).groups() )
            return FlexiDate(y, m, d)
        except AttributeError: # if no match, re.match returns None -> has no attr "groups"
            pass
        
        # now use locale
        string = strings.replace(string, {'/':'-', '.':'-'}) # Recognize all kinds of separators
        try:
            numbers = [int(n) for n in string.split('-')]
            if len(numbers) > 3:
                raise ValueError()
        except ValueError:
            raise ValueError('Invalid date format: "{}"'.format(string))
        FlexiDate._initFormat()
        dateOrder = FlexiDate._dateOrder[len(numbers)-1]
        return FlexiDate(**{key: numbers[i] for i, key in enumerate(dateOrder)})
    
    def strftime(self, format=None):
        """Format the FlexiDate according to the given format. If *format* is None, choose a format based
        on the locale. Otherwise, *format* must be a 3-tuple of format strings, where the first one is used
        if only a year is specified, the second one is used if month and year are specified and the last
        one is used if year, month and day are specified.
        The format strings are python format strings, using the keys Y=year, m=month, d=day.
        """
        if self.month:
            if self.day:
                index = 2
            else: index = 1
        else: index = 0
        
        if format is None:
            FlexiDate._initFormat()    
            format = FlexiDate._dateFormat[index]
        else:
            format = format[index]
        return format.format(Y=self.year, m=self.month, d=self.day)
        
    def toSql(self, maximum=False):
        """Convert this FlexiDate to an int as used to store it in the database."""
        result = 10000*self.year
        if self.month is not None:
            result += 100*self.month
            if self.day is not None:
                result += self.day
        return result

    def endOfYearSql(self):
        """Return the last day of the year of this date as an integer as used in the database."""
        return 10000*self.year + 100*12 + 31
         
    @staticmethod
    def fromSql(value):
        """Create a FlexiDate from an int as used to store FlexiDates in the database."""
        from .. import database
        if value is None:
            return None
        try:
            value = int(value)
            return FlexiDate(value // 10000, (value // 100) % 100, value % 100)
        except ValueError as e:
            raise ValueError("Cannot create a FlexiDate from value {}: {}".format(value, e))

    def __str__(self):
        return self.strftime()

    def __repr__(self):
        if self.month:
            if self.day:
                return "FlexiDate({},{},{})".format(self.year, self.month, self.day)
            else: return "FlexiDate({},{})".format(self.year, self.month)
        else: return "FlexiDate({})".format(self.year)
        
    def __lt__(self, other):
        if not isinstance(other, FlexiDate):
            return NotImplemented
        for a, b in ((self.year, other.year), (self.month, other.month), (self.day, other.day)):
            if a == b:
                continue
            if a is None:
                return True
            if b is None:
                return False
            return a < b
        else: return False # Equality

    def __gt__(self, other):
        if not isinstance(other, FlexiDate):
            return NotImplemented
        return other.__lt__(self)
    
    def __le__(self, other):
        return self == other or self.__lt__(other)
    
    def __ge__(self, other):
        return self == other or self.__gt__(other)
        
    def __eq__(self, other):
        return isinstance(other, FlexiDate) and\
            self.year == other.year and self.month == other.month and self.day == other.day
        
    def __ne__(self, other):
        return not isinstance(other, FlexiDate) or\
            self.year != other.year or self.month != other.month or self.day != other.day

    def __hash__(self):
        return hash((self.year, self.month, self.day))
