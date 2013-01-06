# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
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

translate = QtCore.QCoreApplication.translate
logger = logging.getLogger(__name__)

panels = utils.OrderedDict()


def show(startPanel=None,**params):
    """Open the preferences dialog. To start with a specific panel provide its path as *startPanel*. In this
    case all further keyword arguments will be submitted to the constructor of the start panel.
    """
    from .. import mainwindow
    dialog = PreferencesDialog(mainwindow.mainWindow)
    if startPanel is not None:
        dialog.showPanel(startPanel,**params)
    dialog.exec_()
    
    
class Panel:
    """A panel inside the preferences dialog, i.e. the part on the right of the panel treeview and below of
    the title label. Panels are identified by a path (e.g. "main/tagmanager") and store a class that will be
    instantiated when the panel is shown.
    
    Constructor parameters are
    
        - *path*: A unique identifier for the panel which additionally specifies the parent node in the tree
            of panels.
        - *title*: The title of the panel
        - *theClass*: Either a class or a tuple consisting of a module name
            (e.g. "gui.preferences.tagmanager") and a class name that can be found in the module.
            The module will only be imported when the panel is actully shown.
        
    \ """
    def __init__(self,path,title,theClass):
        self.path = path
        self.title = title
        if isinstance(theClass,type):
            self._theClass = theClass
        else:
            self._importInfo = theClass
            self._theClass = None
        self.subPanels = utils.OrderedDict()
        
    def getClass(self):
        """Return the class of this panel. If import information were submitted to the constructor's
        *theClass* argument instead of a type, this will import the module and find the class when called
        for the first time.
        """
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
    """The preferences dialog contains a list of panels on the left and the current panel's title together
    with the actual panel on the right. Except for the "main" panel which is shown at the beginning, it will
    only construct a panel (and in fact import the corresponding module) when the user selects it in the
    treeview.
    """ 
    # The one single instance
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
        
        # map paths to the widget of a panel once it has been constructed
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
        """Fill the treeview with a tree of all panels."""
        self.treeWidget.clear()
        for path,panel in panels.items():
            item = QtGui.QTreeWidgetItem([panel.title])
            item.setData(0,Qt.UserRole,path)
            self.treeWidget.addTopLevelItem(item)
            if len(panel.subPanels) > 0:
                self._addSubPanels(panel,item)
        
    def _addSubPanels(self,panel,item):
        """Add the subpanels of *panel* to the treeview. *item* is the QTreeWidgetItem for *panel*."""
        for p,subPanel in panel.subPanels.items():
            newPath = '{}/{}'.format(panel.path,p)
            newItem = QtGui.QTreeWidgetItem([subPanel.title])
            newItem.setData(0,Qt.UserRole,newPath)
            item.addChild(newItem)
            if len(subPanel.subPanels) > 0:
                self._addSubPanels(subPanel,newItem)
            item.setExpanded(True)
        
    def showPanel(self,key,**params):
        """Show the panel with the given path, constructing it, if it is shown for the first time.
        In that case additional key-word parameters will be submitted to the constructor."""
        if key not in self.panelWidgets:
            panel = self.getPanel(key)
            innerWidget = panel.getClass()(self,**params)
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
            
    def getPanel(self,path):
        """Return the Panel-instance (not the actual widget!) with the given *path*.""" 
        keys = path.split('/')
        i = 0
        currentPanels = panels
        while i < len(keys) - 1:
            currentPanels = panels[keys[i]].subPanels
            i += 1
        return currentPanels[keys[-1]]
        
    def _handleItemClicked(self,item,column):
        """Handle clicks on a panel in the treeview."""
        key = item.data(0,Qt.UserRole)
        self.showPanel(key)
        
    def _handleFinished(self):
        """Handle the close button."""
        PreferencesDialog._dialog = None
        # Copy the bytearray to avoid memory access errors
        config.binary["preferences_geometry"] = bytearray(self.saveGeometry())


def _getParentPanel(path):
    """Return the parent panel of the one identified by *path*. This method even works when no panel is
    registered for *path* (the parent must be registered, of course)."""
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
    """Add a panel to the preferences dialog. The arguments are passed to the constructor of Panel."""
    insertPanel(path,-1,title,theClass)


def insertPanel(path,position,title,theClass):
    """Insert a panel into the preferences dialog. It will  inserted at the given position into its parent
    in the treeview. If *position* is -1 it will be in inserted at the end. The other arguments are passed
    to the constructor of Panel."""
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
    """Remove the panel with the given path."""
    parent,key = _getParentPanel(path)
    if parent is not None:
        currentPanels = parent.subPanels
    else: currentPanels = panels
    
    if key not in currentPanels:
        raise ValueError("Panel '{}' does not contain a subpanel '{}'".format(parent.path,key))
    del currentPanels[key]
    if PreferencesDialog._dialog is not None:
        PreferencesDialog._dialog.fillTreeWidget()


# Toplevel panels. Map path to Panel instance
panels = utils.OrderedDict()


# Add core panels
addPanel("main",translate("PreferencesPanel","Main"),QtGui.QWidget)
addPanel("main/tagmanager",translate("PreferencesPanel","Tag Manager"),
            ('gui.preferences.tagmanager','TagManager'))
addPanel("main/flagmanager",translate("PreferencesPanel","Flag Manager"),
            ('gui.preferences.flagmanager','FlagManager'))
addPanel("main/delegates",translate("PreferencesPanel","Element display"),
            ('gui.preferences.delegates','DelegatesPanel'))
addPanel("main/filesystem",translate("PreferencesPanel","File system"),
            ('filesystem.preferences', 'FilesystemSettings'))
                   
addPanel("plugins",translate("PreferencesPanel","Plugins"),('plugins.dialog','PluginDialog'))
