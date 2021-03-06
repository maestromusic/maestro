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

import os, shutil, collections
from PyQt5 import QtCore
import taglib
from maestro.core import levels, urls, tags
from maestro import application, logging, config, stack, database as db

translate = QtCore.QCoreApplication.translate
allSources = []


def init():
    from maestro.widgets import WidgetClass
    from maestro import utils
    from maestro.filesystem.browser import FilesystemBrowser
    WidgetClass(
        id='filesystembrowser', theClass=FilesystemBrowser,
        name=translate('FilesystemBrowser', 'File System Browser'),
        icon=utils.images.icon('filesystembrowser'),
        areas='dock', preferredDockArea='right'
    ).register()
    from maestro.filesystem import dialogs
    dialogs.RemoveMissingFilesAction.register('filesystem-removeMissing',
                                              shortcut=translate('QShortcut', 'Del'))
    dialogs.SetPathAction.register('filesystem-setPath')
    dialogs.MissingFilesTreeView.addActionDefinition('filesystem-removeMissing')
    dialogs.MissingFilesTreeView.addActionDefinition('filesystem-setPath')


def enable():
    """Initialize filesystem module. Creates :class:`Source` instances for all configured sources.
    """
    global allSources
    from maestro.filesystem.sources import Source
    allSources = [Source(**data) for data in config.storage.filesystem.sources]
    # delete files not in any source
    if len(allSources) > 0:
        db.query('DELETE FROM {p}newfiles WHERE ' + ' AND '.join('url NOT LIKE "file://{}%"'.format(
                 source.path.replace('"', '\\"')) for source in allSources))
    allSources.sort(key=lambda s: s.name)
    urls.fileBackends.append(RealFile)
    parseAutoReplace()


def disable():
    """Terminates this module, storing the state of all sources."""
    global allSources
    config.storage.filesystem.sources = [s.save() for s in allSources]
    allSources = None


def sourceByName(name):
    for source in allSources:
        if source.name == name:
            return source


def sourceByPath(path):
    for source in allSources:
        if source.contains(path):
            return source


def isValidSourceName(name):
    return name == name.strip() and 0 < len(name) <= 64


def addSource(**data):
    from maestro.filesystem.sources import Source
    source = Source(**data)
    stack.push(translate('Filesystem', 'Add source'),
               stack.Call(_addSource, source), stack.Call(_deleteSource, source))


def _addSource(source):
    allSources.append(source)
    allSources.sort(key=lambda s: s.name)
    application.dispatcher.emit(SourceChangeEvent(application.ChangeType.added, source))


def deleteSource(source):
    stack.push(translate('filesystem', 'Delete source'),
               stack.Call(_deleteSource, source), stack.Call(_addSource, source))


def _deleteSource(source):
    allSources.remove(source)
    application.dispatcher.emit(SourceChangeEvent(application.ChangeType.deleted, source))


def changeSource(source, **data):
    oldData = {attr: getattr(source, attr) for attr in ('name', 'path', 'domain', 'extensions', 'enabled')}
    stack.push(translate('filesystem', "Change source"),
               stack.Call(_changeSource, source, data),
               stack.Call(_changeSource, source, oldData))


def _changeSource(source, data):
    if 'name' in data:
        source.name = data['name']
    if 'path' in data:
        source.setPath(data['path'])
    if 'domain' in data:
        source.domain = data['domain']
    if 'extensions' in data:
        source.setExtensions(data['extensions'])
    if 'enabled' in data:
        source.setEnabled(data['enabled'])
    application.dispatcher.emit(SourceChangeEvent(application.ChangeType.changed, source))


class SourceChangeEvent(application.ChangeEvent):
    """SourceChangeEvent are used when a source is added, changed or deleted."""
    def __init__(self, action: application.ChangeType, source):
        self.action = action
        self.source = source


def getNewfileHash(url):
    """Return the hash of a file specified by *url* which is not yet in the database.

    If the hash is not known, returns None.
    """
    source = sourceByPath(url.path)
    if source and source.enabled and url.path in source.files:
        return source.files[url.path].hash


autoReplaceTags = None


def parseAutoReplace():
    """Parse the config option tags.auto_replace and return a list of tuples (oldname,newname) specifying
    the tags that should be replaced. This does not check whether the tag names are valid."""
    global autoReplaceTags
    string = config.options.tags.auto_replace.replace(' ', '')
    autoReplaceTags = {}
    if len(string) == 0:
        return
    if string[0] != '(' or string[-1] != ')':
        raise ValueError()
    string = string[1:-1]
    autoReplaceTags = {}
    for pair in string.split('),('):
        oldName, newName = pair.split(',') # may raise ValueError
        autoReplaceTags[oldName] = newName


class RealFile(urls.BackendFile):
    """A normal file that is accessed directly on the local filesystem."""

    scheme = 'file'

    def __init__(self, url):
        super().__init__(url)
        self._taglibFile = None

    specialTagNames = 'tracknumber', 'compilation', 'discnumber'

    def readTags(self):
        """Load the tags from disk using pytaglib.

        Special tags (tracknumber, compilation, discnumber) are stored in the "specialTags" attribute.
        """
        self.tags = tags.Storage()
        self.specialTags = collections.OrderedDict()
        try:
            self._taglibFile = taglib.File(self.url.path)
        except OSError:
            if self.url.extension in config.options.main.audio_extensions:
                logging.warning(__name__, 'TagLib failed to open "{}". Tags will be stored in database only'
                                          .format(self.url.path))
            return
        self.length = self._taglibFile.length
        autoProcessingDone = False
        for key, values in self._taglibFile.tags.items():
            key = key.lower()
            if key in self.specialTagNames:
                self.specialTags[key] = values
            elif key in config.options.tags.auto_delete:
                autoProcessingDone = True
                continue
            elif key in autoReplaceTags:
                autoProcessingDone = True
                key = autoReplaceTags[key]
            elif tags.isValidTagName(key):
                tag = tags.get(key)
                validValues = []
                for string in values:
                    try:
                        validValues.append(tag.convertValue(string, crop=True))
                    except tags.TagValueError:
                        logging.error(__name__,
                                      "Invalid value for tag '{}' found: {}".format(tag.name, string))
                if len(validValues) > 0:
                    self.tags.add(tag, *validValues)
            else:
                logging.error(__name__, "Invalid tag name '{}' found : {}".format(key, self.url))
        if autoProcessingDone:
            self.saveTags()

    def rename(self, newUrl):
        if self._taglibFile:
            self._taglibFile = None
        if os.path.exists(newUrl.path):
            raise OSError('Target exists.')
        dir = os.path.dirname(newUrl.path)
        if not os.path.exists(dir):
            os.makedirs(dir)
        shutil.copy2(self.url.path, newUrl.path)
        os.remove(self.url.path)
        try:
            os.removedirs(os.path.dirname(self.url.path))
        except OSError:
            pass
        levels.real.emitFilesystemEvent(renamed=((self.url, newUrl),))
        self.url = newUrl

    def delete(self):
        """Deletes this file from disk. Also removes empty directories."""
        os.remove(self.url.path)
        directory = os.path.dirname(self.url.path)
        if len(os.listdir(directory)) == 0:
            os.removedirs(directory)
        levels.real.emitFilesystemEvent(deleted=(self.url,))

    def saveTags(self):
        """Save what's in self.tags to the file.

        In addition to the tags in self.tags, any ignored tags (TRACKNUMBER etc.) that were read
        using readTags() will be stored in to the file such that they aren't lost.

        If some tags cannot be saved due to restrictions of the underlying metadata format, those
        tags/values that remain unsaved will be returned.
        """
        if not self._taglibFile:
            raise OSError('Unable to write tags to file {}'.format(self.url.path))
        self._taglibFile.tags = dict()
        for tag, values in self.specialTags.items():
            self._taglibFile.tags[tag.upper()] = values
        for tag, values in self.tags.items():
            values = sorted(tag.fileFormat(value) for value in values)
            self._taglibFile.tags[tag.name.upper()] = values
        unsuccessful = self._taglibFile.save()
        ret = {key.upper(): values for key,values in unsuccessful.items()}
        levels.real.emitFilesystemEvent(modified=(self.url,))
        return ret
