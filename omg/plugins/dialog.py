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
from . import PLUGINDIR, enabledPlugins, enablePlugin, disablePlugin

translate = QtCore.QCoreApplication.translate

logger = logging.getLogger("omg.plugins")

PLUGININFO_KEYS = ["name","author","version","description"]
COLUMN_HEADERS = [translate("PluginDialog","Enabled"),
                  translate("PluginDialog","Name"),translate("PluginDialog","Author"),
                  translate("PluginDialog","Version"),translate("PluginDialog","Description")
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

        allData = self.loadData()
        allData.sort(key=lambda el: el[1]["name"].lower())
        self.pluginNames = [el[0] for el in allData]
        
        self.table.setRowCount(len(allData))
        self.table.setColumnCount(len(PLUGININFO_KEYS)+1)
        self.table.setHorizontalHeaderLabels(COLUMN_HEADERS)
        self.table.verticalHeader().hide()
        
        for i,data in enumerate(allData):
            pluginName,data = data
            item = QtGui.QTableWidgetItem()
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if pluginName in enabledPlugins else Qt.Unchecked)
            self.table.setItem(i,0,item)
            for j,key in enumerate(PLUGININFO_KEYS):
                item = QtGui.QTableWidgetItem(data[key])
                item.setFlags(Qt.ItemIsEnabled)
                self.table.setItem(i,j+1,item)
        self.table.resizeColumnsToContents()

        # Connect at the end so _handleCellChanged is not called when the cells are initialized
        self.table.cellChanged.connect(self._handleCellChanged)

    def loadData(self):
        """Load plugin data from the PLUGININFO files. Return it as tuple (plugin directory,PLUGININFO data), where the second entry is a dict mapping the keys from PLUGININFO_KEYS to the corresponding value in the file."""
        data = []
        for pluginName in os.listdir(PLUGINDIR):
            dir = os.path.join(PLUGINDIR,pluginName)
            if os.path.isdir(dir):
                filePath = os.path.join(dir,"PLUGININFO")
                if os.path.exists(filePath) and os.path.isfile(filePath):
                    data.append((pluginName,self.readFile(filePath)))
        return data

    def readFile(self,path):
        """Read the file with the given path and return a dict mapping the keys from PLUGININFO_KEYS to the corresponding value in the file."""
        try:
            with open(path,"r") as file:
                data = {}
                for line in file:
                    key,value = line.split("=",1)
                    key = key.strip().lower()
                    value = value.strip()
                    if key in PLUGININFO_KEYS:
                        data[key] = value
                    else: logger.warning("Unknown key '{}' in {}".format(key,path))

                for key in PLUGININFO_KEYS:
                    if key not in data:
                        logger.warning("Missing key '{}' in {}".format(key,path))
                        data[key] = ""
                return data
        except IOError:
            return {k:"" for k in PLUGININFO_KEYS}

    def close(self):
        # Copy the bytearray to avoid memory access errors
        config.binary["pluginwindow_geometry"] = bytearray(self.saveGeometry())
        QtGui.QDialog.close(self)

    def _handleCellChanged(self,row,column):
        """Enable or disable plugins when the check state of a plugin has been changed."""
        if column == 0:
            pluginName = self.pluginNames[row]
            item = self.table.item(row,column)
            if pluginName in enabledPlugins and item.checkState() == Qt.Unchecked:
                disablePlugin(pluginName)
            elif pluginName not in enabledPlugins and item.checkState() == Qt.Checked:
                enablePlugin(pluginName)
