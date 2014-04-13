# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2014 Martin Altmayer, Michael Helmling
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

import os, os.path, datetime, itertools, collections
from .. import config

        
def hasKnownExtension(file):
    """Return True if the given path has a known extension (i.e., appears in options.main.extension).
    Does **not** check whether the file actually exists, is readable, etc."""
    s = file.rsplit(".", 1)
    if len(s) == 1:
        return False
    else:
        return s[1].lower() in config.options.main.extensions
    
    
def relPath(file):
    """Return the relative path of a music file against the collection base path."""
    if os.path.isabs(file):
        return os.path.relpath(file, config.options.main.collection)
    else:
        return file


def absPath(file):
    """Return the absolute path of a music file inside the collection directory, if it is not absolute
    already."""
    if not os.path.isabs(file):
        return os.path.join(config.options.main.collection, file)
    else:
        return file


def mTimeStamp(url):
    """Get the modification timestamp of a file given by *url* as UTC datetime."""
    return datetime.datetime.fromtimestamp(os.path.getmtime(url.absPath),
                                           tz=datetime.timezone.utc).replace(microsecond=0)


def collect(urls):
    """Find all music files below the given QUrls. This is used in various dropMimeData methods when urls
    are received. Return a dict mapping directory to list of FileURLs within. Sort directories and files.
    """
    from ..filebackends.filesystem import FileURL
    filePaths = collections.OrderedDict()
    
    def add(file, parent=None):
        if not hasKnownExtension(file):
            return
        dir = parent or os.path.dirname(file)
        if dir not in filePaths:
            filePaths[dir] = []
        filePaths[dir].append(FileURL(file))
        
    for url in urls:
        path = url.path()
        if os.path.isfile(path):
            add(path)
        else:
            for parent, dirs, files in os.walk(path):
                for f in files:
                    add(os.path.join(parent, f), parent)
                dirs.sort()
        
    from . import PointAtInfinity
    def sortFunction(url):
        dir, file = os.path.split(url.path)
        i = 0
        while file[i].isdigit():
            i += 1
        if i == 0:
            return (dir, PointAtInfinity(), file)
        else: return (dir, int(file[:i]), file[i:], file)
                
    for files in filePaths.values():
        files.sort(key=sortFunction)

    return filePaths


def collectAsList(urls):
    """Find all music files below the given QUrls. This is used in various dropMimeData methods when urls
    are received. Return a list of FileURLs. Sort files within each directory, but not the list as whole.
    """
    from ..filebackends.filesystem import FileURL
    def checkUrl(url):
        path = url.path()
        if os.path.isfile(path):
            if hasKnownExtension(path):
                return [FileURL(path)]
            else: return []
        else: return itertools.chain.from_iterable(collect([url]).values())
    return itertools.chain.from_iterable(checkUrl(url) for url in urls)
