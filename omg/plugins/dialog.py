# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

"""This module provides a dialog to display all plugins with the info from the PLUGININFO file and allow the user to enable or disable them."""

import os, sys

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

from omg import logging, config, constants
from . import PLUGINDIR, PLUGININFO_OPTIONS, plugins

translate = QtCore.QCoreApplication.translate

logger = logging.getLogger("omg.plugins")

COLUMN_HEADERS = [translate("PluginDialog","Enabled"),
                  translate("PluginDialog","Name"),translate("PluginDialog","Author"),
                  translate("PluginDialog","Version"),translate("PluginDialog","Description"),
                  translate("PluginDialog","Minimum OMG version"), translate("PluginDialog", "Maximum OMG version")
                  ]


class PluginDialog(QtGui.QDialog):
    """Dialog to display all plugins with the info from the PLUGININFO file and allow the user to enable or disable them."""
    def __init__(self,parent=None):
        QtGui.QDialog.__init__(self,parent)
        self.setLayout(QtGui.QVBoxLayout())
        self.setWindowTitle("OMG version {} – Plugins".format(constants.VERSION))
        if "pluginwindow_geometry" in config.binary and isinstance(config.binary["mainwindow_geometry"],bytearray):
            success = self.restoreGeometry(config.binary["pluginwindow_geometry"])
        else: success = False
        if not success: # Default geometry
            self.resize(900,500)
            # Center the window
            screen = QtGui.QDesktopWidget().screenGeometry()
            size = self.geometry()
            self.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)

        self.layout().addWidget(QtGui.QLabel(self.tr("Warning: Changes will be performed immediately!")))
        self.table = QtGui.QTableWidget()
        self.layout().addWidget(self.table,1)

        buttonLayout = QtGui.QHBoxLayout()
        self.layout().addLayout(buttonLayout)
        buttonLayout.addStretch(1)
        closeButton = QtGui.QPushButton(QtGui.QIcon.fromTheme('window-close'),self.tr("Close"))
        closeButton.clicked.connect(self.close)
        buttonLayout.addWidget(closeButton,0)
        
        self.table.setRowCount(len(plugins))
        self.table.setColumnCount(len(PLUGININFO_OPTIONS)+1)
        self.table.setHorizontalHeaderLabels(COLUMN_HEADERS)
        self.table.verticalHeader().hide()
        
        for i,plugin in enumerate(plugins.values()):
            item = QtGui.QTableWidgetItem()
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable if plugin.version_ok else Qt.NoItemFlags)
            item.setCheckState(Qt.Checked if plugin.enabled else Qt.Unchecked)
            self.table.setItem(i,0,item)
            for j,key in enumerate(PLUGININFO_OPTIONS):
                item = QtGui.QTableWidgetItem(plugin.data[key])
                item.setFlags(Qt.ItemIsEnabled if plugin.version_ok else Qt.NoItemFlags)
                self.table.setItem(i,j+1,item)
        self.table.resizeColumnsToContents()

        # Connect at the end so _handleCellChanged is not called when the cells are initialized
        self.table.cellChanged.connect(self._handleCellChanged)

    def close(self):
        # Copy the bytearray to avoid memory access errors
        config.binary["pluginwindow_geometry"] = bytearray(self.saveGeometry())
        QtGui.QDialog.close(self)

    def _handleCellChanged(self,row,column):
        """Enable or disable plugins when the check state of a plugin has been changed."""
        if column == 0:
            plugin = list(plugins.values())[row]
            item = self.table.item(row,column)
            if plugin.enabled and item.checkState() == Qt.Unchecked:
                plugin.disable()
            elif not plugin.enabled and item.checkState() == Qt.Checked:
                plugin.enable()
