# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2015 Martin Altmayer, Michael Helmling
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

import abc
import os.path
import re
from PyQt4 import QtCore
from maestro import utils

translate = QtCore.QCoreApplication.translate
fileBackends = []


class URL:
    """Each File in Maestro is identified by an URL of the form <scheme>://<netloc>/<path>. Different schemes
    can represent different backends for handling the files on filesystem level.
    """
    urlRegex = re.compile(r'(\w+)://(\w*)(/.*)')

    def __init__(self, urlString):
        self.scheme, self.netloc, self.path = URL.urlRegex.match(urlString).groups()

    def __str__(self):
        return '{}://{}{}'.format(self.scheme, self.netloc, self.path)

    @classmethod
    def fileURL(cls, path):
        """Convenience method: create an URL with scheme 'file', empty netloc and given *path*."""
        assert path[0] == '/'
        return cls('file://{}'.format(path))

    @property
    def extension(self) -> str:
        """Returns the lowercased extension of the URL, i.e., part of the path after the final dot, or None if
        if there's no dot in the path."""
        ext = os.path.splitext(self.path)[1]
        if len(ext) > 1:
            return ext[1:].lower()
        return None

    def backendFile(self):
        """Create and return a BackendFile object matching this URL.
        """
        for cls in fileBackends:
            try:
                return cls(self)
            except UnsupportedSchemeException:
                pass
        raise UnsupportedSchemeException('No backend succeeded to load URL {}'.format(self))

    @property
    def directory(self):
        return os.path.dirname(self.path)

    def toQUrl(self):
        return QtCore.QUrl(str(self))

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, other):
        return str(self) == str(other)

    def __neq__(self, other):
        return str(self) != str(other)

    def __repr__(self):
        return 'URL({})'.format(str(self))


class UnsupportedSchemeException(Exception):
    """Exception thrown by BackendFile implementations when a URL with unsupported scheme was supplied."""
    pass


class TagWriteError(RuntimeError):
    """An error that is raised when writing tags to a BackendFile fails."""

    def __init__(self, url, problems=None):
        super().__init__("Error writing tags of {}".format(url))
        self.url = url
        self.problems = problems

    def displayMessage(self):
        from ..gui import dialogs
        title = translate("TagWriteError", "Error saving tags")
        msg1 = translate("TagWriteError", "Could not write tags of file {}:\n").format(self.url)
        msgReadonly = translate("TagWriteError", "File is readonly")
        msgProblem = translate("TagWriteError", "Tags '{}' not supported by format").format(self.problems)
        dialogs.warning(title, msg1 + (msgReadonly if self.problems is None else msgProblem))


class BackendFile(metaclass=abc.ABCMeta):
    """Abstract base for a file representation in a specific backend."""

    scheme = None

    def __init__(self, url: URL):
        """Initialize the backend file, but don't read any tags etc."""
        if url.scheme != self.scheme:
            raise UnsupportedSchemeException('{} needs "{}" scheme URL'.format(type(self), self.scheme))
        self.tags = None
        self.url = url
        self.length = 0
        self.position = None

    @abc.abstractmethod
    def readTags(self):
        """Read the tags which will be available in the *tags* attribute afterwards."""
        pass

    def saveTags(self):
        """Store any changes made to the tags. May return a sub-storage of failures."""
        raise OSError('Saving tags is not supported by file backend {}'.format(type(self)))

    def rename(self, newPath):
        raise OSError('Renaming not supported by file backend {}'.format(type(self)))

    def delete(self):
        raise OSError('Deleting not supported by file backend {}'.format(type(self)))


def changeTags(changes):
    """Change tags of files. If an error occurs, all changes are undone and a TagWriteError is raised.

    *changes* is a dict mapping elements or BackendFiles to TagDifferences. If the dict contains elements
    only the corresponding BackendFiles will be changed! This method does not touch the element instances
    or the database. Containers will be skipped.
    All BackendFiles contained in the dict must already have loaded their tags.
    """
    from maestro.core import elements
    doneFiles = []
    rollback = False
    problems = None
    for elementOrFile, diff in changes.items():
        if isinstance(elementOrFile, elements.Element):
            if not elementOrFile.isFile() or not utils.files.isMusicFile(elementOrFile.url.path):
                continue
            backendFile = elementOrFile.url.backendFile()
            backendFile.readTags()
        elif not utils.files.isMusicFile(elementOrFile.url.path):
            continue
        else:
            backendFile = elementOrFile
        if not utils.files.isMusicFile(elementOrFile.url.path):
            return

        currentFileTags = backendFile.tags.copy()
        diff.apply(backendFile, withoutPrivateTags=True)
        problems = backendFile.saveTags()
        if problems:
            problemUrl = backendFile.url
            backendFile.tags = currentFileTags
            backendFile.saveTags()
            rollback = True
        else:
            doneFiles.append((backendFile, diff))

    if rollback:
        for backendFile, diff in doneFiles:
            diff.revert(backendFile.tags, withoutPrivateTags=True)
            backendFile.saveTags()
        raise TagWriteError(problemUrl, problems)