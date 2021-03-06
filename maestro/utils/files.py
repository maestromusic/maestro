# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2014-2015 Martin Altmayer, Michael Helmling
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

import os, os.path, itertools, collections, re
from maestro import config
    

def isMusicFile(path):
    """Return whether the given file is a music file. This check looks only on the file extension."""
    _, ext = os.path.splitext(path)
    if not ext.startswith('.'):
        return False
    return ext[1:].lower() in config.options.main.audio_extensions


def collect(qUrls):
    """Find all music files below the given QUrls. This is used in various dropMimeData methods when urls
    are received. Return a dict mapping directory to list of URLs within. Sort directories and files.
    """
    filePaths = collections.OrderedDict()
    from maestro.core import urls

    def add(file, parent=None):
        dir = parent or os.path.dirname(file)
        if dir not in filePaths:
            filePaths[dir] = []
        filePaths[dir].append(urls.URL.fileURL(file))
        
    for url in qUrls:
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


def collectAsList(listOfUrls):
    """Find all music files below the given QUrls. This is used in various dropMimeData methods when
    urls are received. Return a list of URLs. Sort files within each directory, but not the list
    as whole.
    """
    from maestro.core import urls
    def checkUrl(url):
        path = url.path()
        if os.path.isfile(path):
            return [urls.URL.fileURL(path)]
        else:
            return itertools.chain.from_iterable(collect([url]).values())

    return itertools.chain.from_iterable(checkUrl(url) for url in listOfUrls)


def splitPath(path, includeRoot=True):
    """Split a path: '/home/maestro/Music' becomes ['/', 'home', 'maestro', 'Music']."""
    components = []
    while True:
        basePath, c = os.path.split(path)
        if basePath == '':
            components.insert(0, c)
            break
        elif c == '':
            if includeRoot:
                components.insert(0, path)
            break
        else:
            components.insert(0, c)
            path = basePath
    return components


def makeFilePath(folder, fileName, forceAscii=False, maxLength=120, exists=os.path.exists):
    """Return a file path that is similar to os.path.join(folder,fileName), but
        - weird special characters will be removed,
        - the path does not exist yet (or numbers will be appended before the extension to guarantee this),
        - if *forceAscii* is true, the path will only contain ASCII characters,
        - including the numbers from above and the extension the file name (not the whole path)
          has at most *maxLength* characters. 120 is a sensible max length; the real max length is
          platform-dependent, but not important.

    The argument *exists* is used to test whether a path exists. It must be a function taking an absolute
    path as argument and returning a bool. The default 'os.path.exists' should work in most cases, but
    for virtual filesystems other functions are necessary.
    """
    fileName, extension = os.path.splitext(fileName)
    
    # Handle unicode characters
    if forceAscii:
        # How to automatically replace characters by their closest ASCII character?
        # unicodedata.normalize('NFKD') represents characters like e.g. 'á' in its decomposed form '´a'.
        # Since the accent is a 'combining accent' it will be combined with the letter automatically and
        # you won't see the difference unless you check the length of the string.
        # encode('ascii', 'ignore') throws all those scary characters away.
        import unicodedata
        fileName = unicodedata.normalize('NFKD', fileName).encode('ascii', 'ignore').decode()
    
    # Remove weird characters and weird use of whitespace
    fileName = re.sub('[^\w\s_-]', '', fileName).strip()
    fileName = re.sub('\s+', ' ', fileName)
    
    # In the easiest form, the following simply adds the extension and returns the path.
    # Actually it deals with two problems that may arise:
    # - The filename may be too long
    # - The filename may exist already
    # To solve the first problem, the fileName is shortened, to solve the second one we append '_n' for some
    # number n to the filename (but in front of the extension)
    # We do this until we have found a valid and non-existent filename.
    i = -1
    currentExt = extension # currentExt is the suffix together with the extension
    while True:
        i += 1
        currentExt = extension if i == 0 else '_{}{}'.format(i, extension)
        if len(fileName.encode()) + len(currentExt.encode()) > maxLength:
            length = maxLength - len(currentExt.encode())
            # ignore errors that may arise from cropping the string inside a multibyte character
            fileName = fileName.encode()[:length].decode('utf-8', 'ignore')
            continue
        
        path = os.path.join(folder, fileName+currentExt)
        if not exists(path):
            return path
