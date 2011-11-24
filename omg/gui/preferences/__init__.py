# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2011 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

from ... import utils, logging, config
from . import tagmanager, flagmanager
from ...plugins import dialog as plugindialog

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)

panels = utils.OrderedDict()


def show(parent,startPanel=None):
    dialog = PreferencesDialog(parent)
    if startPanel is not None:
        dialog.showPanel(startPanel)
    dialog.exec_()
    
    
class Panel:
    def __init__(self,path,title,theClass,subPanels=None):
        self.path = path
        self.title = title
        if isinstance(theClass,type):
            self._theClass = theClass
        else:
            self._importInfo = theClass
            self._theClass = None
        if subPanels is None:
            self.subPanels = utils.OrderedDict()
        else: self.subPanels = utils.OrderedDict.fromItems(subPanels)
        
    def getClass(self):
        if self._theClass is None:
            import importlib
            try:
                module = importlib.import_module('.'+self._importInfo[0],'omg')
                self._theClass = getattr(module,self._importInfo[1])
            except ImportError:
                logger.error("Cannot import module '{}'".format(self._importInfo[0]))
                self._theClass = QtGui.QWidget
            except AttributeError:
                logger.error("Module '{}' has no attribute '{}'".format(*self._importInfo))
                self._theClass = QtGui.QWidget 
        return self._theClass
        
        
class PreferencesDialog(QtGui.QDialog):
    _dialog = None
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Preferences - OMG"))
        self.finished.connect(self._handleFinished)

        # Restore geometry
        if ("preferences_geometry" in config.binary and
                isinstance(config.binary["preferences_geometry"],bytearray)):
            success = self.restoreGeometry(config.binary["preferences_geometry"])
        else:
            success = False
        if not success: # Default geometry
            self.resize(800,600)
        
        self.panelWidgets = {}
        
        self.setLayout(QtGui.QVBoxLayout())
        
        splitter = QtGui.QSplitter(Qt.Horizontal)
        self.layout().addWidget(splitter,1)
        
        self.treeWidget = QtGui.QTreeWidget()
        self.treeWidget.header().setVisible(False)
        self.treeWidget.itemClicked.connect(self._handleItemClicked)
        splitter.addWidget(self.treeWidget)
        
        self.stackedWidget = QtGui.QStackedWidget()
        splitter.addWidget(self.stackedWidget)
        
        splitter.setSizes([150,650])
        
        self.fillTreeWidget()
        self.showPanel("main")
        PreferencesDialog._dialog = self
        
    def fillTreeWidget(self):
        self.treeWidget.clear()
        for key,panel in panels.items():
            item = QtGui.QTreeWidgetItem([panel.title])
            item.setData(0,Qt.UserRole,key)
            self.treeWidget.addTopLevelItem(item)
            if len(panel.subPanels) > 0:
                self._addSubPanels(key,panel,item)
        
    def _addSubPanels(self,key,panel,item):
        for k,subPanel in panel.subPanels.items():
            newKey = '/'.join([key,k])
            newItem = QtGui.QTreeWidgetItem([subPanel.title])
            newItem.setData(0,Qt.UserRole,newKey)
            item.addChild(newItem)
            if len(subPanel.subPanels) > 0:
                self._addSubPanels(newKey,subPanel,newItem)
            item.setExpanded(True)
        
    def showPanel(self,key):
        if key not in self.panelWidgets:
            panel = self.getPanel(key)
            innerWidget = panel.getClass()(self)
            widget = QtGui.QWidget()
            widget.setLayout(QtGui.QVBoxLayout())
            label = QtGui.QLabel(panel.title)
            font = label.font()
            font.setPointSize(16)
            font.setBold(True)
            label.setFont(font)
            widget.layout().addWidget(label,0)
            widget.layout().addWidget(innerWidget,1)
            #frame = QtGui.QFrame()
            #frame.setFrameShape(QtGui.QFrame.HLine)
            #widget.layout().addWidget(frame)
            self.panelWidgets[key] = widget
            self.stackedWidget.addWidget(widget)
        self.stackedWidget.setCurrentWidget(self.panelWidgets[key])
            
    def getPanel(self,key):
        keys = key.split('/')
        i = 0
        currentPanels = panels
        while i < len(keys) - 1:
            currentPanels = panels[keys[i]].subPanels
            i += 1
        return currentPanels[keys[-1]]
        
    def _handleItemClicked(self,item,column):
        key = item.data(0,Qt.UserRole)
        self.showPanel(key)
        
    def _handleFinished(self):
        PreferencesDialog._dialog = None
        # Copy the bytearray to avoid memory access errors
        config.binary["preferences_geometry"] = bytearray(self.saveGeometry())


def _getParentPanel(path):
    keys = path.split('/')
    i = 0
    parent = None
    currentPanels = panels
    while i < len(keys) - 1:
        if keys[i] not in currentPanels:
            raise ValueError("Panel '{}' does not contain a subpanel '{}'".format('/'.join(keys[:i]),keys[i]))
        parent = currentPanels[keys[i]]
        currentPanels = parent.subPanels
        i += 1
    
    return parent,keys[-1]
    
    
def addPanel(path,title,theClass):
    insertPanel(path,-1,title,theClass)


def insertPanel(path,position,title,theClass):
    parent,key = _getParentPanel(path)
    if parent is not None:
        currentPanels = parent.subPanels
    else: currentPanels = panels
        
    if key in currentPanels:
        raise ValueError("Panel '{}' does already exist".format('/'.join(keys)))
    if position == -1:
        position = len(currentPanels)
    currentPanels.insert(position,key,Panel(path,title,theClass))
    if PreferencesDialog._dialog is not None:
        PreferencesDialog._dialog.fillTreeWidget()


def removePanel(path):
    parent,key = _getParentPanel(path)
    if parent is not None:
        currentPanels = parent.subPanels
    else: currentPanels = panels
    
    if key not in currentPanels:
        raise ValueError("Panel '{}' does not contain a subpanel '{}'".format(parent.path,key))
    del currentPanels[key]
    if PreferencesDialog._dialog is not None:
        PreferencesDialog._dialog.fillTreeWidget()


panels = utils.OrderedDict()

addPanel("main",translate("PreferencesPanel","Main"),QtGui.QWidget)
addPanel("main/tagmanager",translate("PreferencesPanel","Tag Manager"),
            ('gui.preferences.tagmanager','TagManager'))
addPanel("main/flagmanager",translate("PreferencesPanel","Flag Manager"),
            ('gui.preferences.flagmanager','FlagManager'))
addPanel("main/delegates",translate("PreferencesPanel","Element display"),
            ('gui.preferences.delegates','DelegatesPanel'))
                   
addPanel("plugins",translate("PreferencesPanel","Plugins"),plugindialog.PluginDialog)
