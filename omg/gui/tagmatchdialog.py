# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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

"""This module contains a dialog that matches tags from paths of files by a format string with placeholders."""

import re

from PyQt4 import QtCore, QtGui

from .. import modify, config
from ..core import tags


class ExtendedTableWidgetItem(QtGui.QTableWidgetItem):
    """A QTableWidgetItem with an additional internal object pointer."""
    def __init__(self, object, text = None):
        super().__init__(text)
        self.internalPointer = object
        
class TagMatchDialog(QtGui.QDialog):
    def __init__(self, level, elements, parent = None):
        super().__init__(parent)
        self.setModal(True)
        self.level = level
        self.setWindowTitle('Tag Match Dialog')
        firstLine = QtGui.QHBoxLayout()
        firstLine.addWidget(QtGui.QLabel('Format string:'))
        self.formatEdit = QtGui.QLineEdit(config.storage.editor.format_string)
        self.formatEdit.setToolTip(self.tr('Tag placeholders must be written in the form %{tagname}. The special '
                                         + 'placeholder %{*} matches any text which is not to be matched to a tag '
                                         + '(like file extensions)' ))
        firstLine.addWidget(self.formatEdit)
        self.formatEdit.textChanged.connect(self.updateMatch)
        lay = QtGui.QVBoxLayout()
        lay.addLayout(firstLine)
        
        self.table = QtGui.QTableWidget(len(elements), 2)
        self.table.setHorizontalHeaderLabels([self.tr('file path'), self.tr('proposed tags')])
        self.table.setGridStyle(QtCore.Qt.NoPen)
        lay.addWidget(self.table)
        for i,el in enumerate(elements):
            item = ExtendedTableWidgetItem(el, el.path)
            item.setFlags(QtCore.Qt.ItemIsEnabled)
            self.table.setItem(i,0, item)
            item = ExtendedTableWidgetItem(None)
            item.setFlags(QtCore.Qt.ItemIsEnabled)
            self.table.setItem(i,1, item)
        self.table.resizeColumnsToContents()
        buttonLine = QtGui.QHBoxLayout()
        self.keepOtherTagsCheckbox = QtGui.QCheckBox(self.tr('keep other existing tags'))
        self.keepOtherTagsCheckbox.setChecked(True)
        self.keepOtherTagsCheckbox.setToolTip(self.tr('If this is checked and the files already contain tags not appearing in the format '
         + 'string, these are kept. Otherwise all existing tags are deleted.'))
        okButton = QtGui.QPushButton('OK')
        okButton.clicked.connect(self.commitChanges)
        cancelButton = QtGui.QPushButton('Cancel')
        cancelButton.clicked.connect(self.reject)
        buttonLine.addWidget(self.keepOtherTagsCheckbox)
        buttonLine.addStretch()
        buttonLine.addWidget(cancelButton)
        buttonLine.addWidget(okButton)
        lay.addLayout(buttonLine)
        self.setLayout(lay)
        self.resize(1200,600)
        self.updateMatch()
    
    def updateMatch(self):
        formatString = self.formatEdit.text()
        notRegexp = '(?:.*/)?' + re.sub('(.*?)(%\{.+?\})', lambda b: re.escape(b.group(1)) + b.group(2), formatString)
        theRegexp = re.sub('\%\{(\w+)\}','(?P<\g<1>>.+)', notRegexp).replace('%{*}', '.*')
        for i in range(self.table.rowCount()):
            m = re.match(theRegexp, self.table.item(i,0).text())
            if m:
                self.table.item(i, 1).internalPointer = m.groupdict()
                self.table.item(i, 1).setText(", ".join('{0}={1}'.format(a,b) for a,b in m.groupdict().items()))
            else:
                self.table.item(i,1).setText('match failed')
        self.table.resizeColumnsToContents()
        
    def commitChanges(self):
        config.storage.editor.format_string = self.formatEdit.text()
        modify.beginEditorMacro(self.tr('match tags from filenames'))
        for row in range(self.table.rowCount()):
            element = self.table.item(row, 0).internalPointer
            tagDict = self.table.item(row, 1).internalPointer
            elementAfter = element.copy()
            if not self.keepOtherTagsCheckbox.isChecked():
                elementAfter.tags = tags.Storage()
            for tag, value in tagDict.items():
                if tag == 'tracknumber':
                    elementAfter.position = int(value)
                else:
                    elementAfter.tags[tags.get(tag)] = [value]
            modify.push(modify.ModifySingleElementCommand(self.level, element, elementAfter))
        modify.endEditorMacro()
        self.accept()