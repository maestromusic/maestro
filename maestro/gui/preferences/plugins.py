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

"""This module provides a dialog to display all plugins with the info from the PLUGININFO file and allow
the user to enable or disable them."""

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from ... import plugins

translate = QtCore.QCoreApplication.translate


PLUGININFO_OPTIONS = ("NAME", "AUTHOR", "VERSION", "DESCRIPTION", "MINVERSION", "MAXVERSION")


COLUMN_HEADERS = [translate("PluginDialog", "Enabled"),
                  translate("PluginDialog", "Name"),
                  translate("PluginDialog", "Author"),
                  translate("PluginDialog", "Version"),
                  translate("PluginDialog", "Description"),
                  translate("PluginDialog", "Minimum Maestro version"),
                  translate("PluginDialog", "Maximum Maestro version")
                  ]


class PluginPanel(QtWidgets.QWidget):
    """Preferences panel to display all plugins with the info from the PLUGININFO file and allow the user to
    enable or disable them."""
    def __init__(self, dialog, panel):
        super().__init__(panel)
        self.setLayout(QtWidgets.QVBoxLayout())
            
        self.table = QtWidgets.QTableWidget()
        self.layout().addWidget(self.table, 1)
        self.table.setRowCount(len(plugins.plugins))
        self.table.setColumnCount(len(PLUGININFO_OPTIONS)+1)
        self.table.setHorizontalHeaderLabels(COLUMN_HEADERS)
        self.table.verticalHeader().hide()
        
        for i, plugin in enumerate(plugins.plugins.values()):
            item = QtWidgets.QTableWidgetItem()
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable if plugin.versionOk else Qt.NoItemFlags)
            item.setCheckState(Qt.Checked if plugin.enabled else Qt.Unchecked)
            self.table.setItem(i, 0, item)
            for j, key in enumerate(PLUGININFO_OPTIONS):
                if hasattr(plugin.package, key):
                    text = getattr(plugin.package, key)
                else: text = ''
                item = QtWidgets.QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsEnabled if plugin.versionOk else Qt.NoItemFlags)
                self.table.setItem(i, j+1, item)
        self.table.resizeColumnsToContents()

        # Connect at the end so _handleCellChanged is not called when the cells are initialized
        self.table.cellChanged.connect(self._handleCellChanged)

    def _handleCellChanged(self, row, column):
        """Enable or disable plugins when the check state of a plugin has been changed."""
        if column == 0:
            plugin = list(plugins.plugins.values())[row]
            item = self.table.item(row, column)
            if plugin.enabled and item.checkState() == Qt.Unchecked:
                plugin.disable()
            elif not plugin.enabled and item.checkState() == Qt.Checked:
                try:
                    plugin.enable()
                    plugin.mainWindowInit()
                except Exception as e:
                    item.setCheckState(False)
                    from ..dialogs import warning
                    warning(self.tr("Error enabling plugin"),
                            self.tr("Could not enable plugin {}:\n{}")
                            .format(plugin.name, e))
