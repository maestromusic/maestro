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

"""
The InstallTool is opened when an important config variable is missing, when the database connection fails
and in similar cases. It contains several pages of configuration widgets. When enough information is
collected it will connect to the database and create the tables (if the database is empty) and fill them with
initial tags (in particular the special tags title and album).

Currently the order of pages is:

1. Language
2. Domain settings
3. Database settings (depends on the chosen database type)
4. (optional). Either
    Tags settings (if the tagids table is empty; allows to choose initial tags)
    or
    Special tags settings (if tagids is not empty, but either 'title' or 'album' are missing)
"""
import collections, os

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt

# This script tries to include as few modules as possible
from maestro import config, logging, database as db
from maestro.application import loadTranslators
from maestro.core.tags import isValidTagName
from maestro.core.domains import isValidName as isValidDomainName
from maestro.gui import flexform

logger = logging.getLogger("Install tool")


class InstallToolWindow(QtGui.QWidget):
    """The InstallToolWindow contains several pages/states/SettingsWidgets which allow the user to define
    basic config variables and set up the database.
    
    The order in which the states are displayed may depend on the configuration (e.g. only one of sqlite or
    mysql is shown) and is figured out in _handleNextButton.
    """
    # List of all states/pages
    states = ['language', 'database', 'domains', 'tags', 'audio']
    # Mapping state name to the corresponding SettingsWidget
    stateWidgets = {}
    # Current state
    state = 'language'
    
    def __init__(self):
        super().__init__()
        
        config.init()
        logging.init()
        
        loadTranslators(app, logger)
        self.setWindowTitle(self.tr("Maestro Install Tool"))
        self.resize(630, 550)
        self.move(QtGui.QApplication.desktop().screen().rect().center() - self.rect().center())
        
        layout = QtGui.QVBoxLayout(self)
        
        self.stackedLayout = QtGui.QStackedLayout()
        layout.addLayout(self.stackedLayout)
        
        buttonLayout = QtGui.QHBoxLayout()
        style = QtGui.QApplication.style()
        layout.addLayout(buttonLayout)
        self.prevButton = QtGui.QPushButton(self.tr("Previous"))
        self.prevButton.setIcon(style.standardIcon(QtGui.QStyle.SP_ArrowLeft))
        self.prevButton.clicked.connect(self._handlePrevButton)
        self.prevButton.setEnabled(False)
        buttonLayout.addWidget(self.prevButton)
        buttonLayout.addStretch()
        self.nextButton = QtGui.QPushButton(self.tr("Next"))
        self.nextButton.setIcon(style.standardIcon(QtGui.QStyle.SP_ArrowRight))
        self.nextButton.clicked.connect(self._handleNextButton)
        self.nextButton.setDefault(True)
        buttonLayout.addWidget(self.nextButton)
        
        self.stateWidgets['language'] = LanguageWidget(self, 1)
        self.stackedLayout.addWidget(self.stateWidgets['language'])
        # All other widgets are not created until the language is chosen
        
    def createOtherWidgets(self):
        """Create all settings widgets except for the language widget."""
        self.stateWidgets['database'] = DatabaseWidget(self, 2)
        self.stackedLayout.addWidget(self.stateWidgets['database'])
        
        self.stateWidgets['domains'] = DomainWidget(self, 3)
        self.stackedLayout.addWidget(self.stateWidgets['domains'])
        
        self.stateWidgets['tags'] = TagWidget(self, 4)
        self.stackedLayout.addWidget(self.stateWidgets['tags'])
        
        self.stateWidgets['audio'] = AudioWidget(self, 5)
        self.stackedLayout.addWidget(self.stateWidgets['audio'])
    
    def showState(self, state):
        """Display the settingsWidget for the given state (from the list self.states)."""
        self.state = state
        self.stackedLayout.setCurrentWidget(self.stateWidgets[state])
        self.prevButton.setEnabled(self.state not in ['language', 'database'])
        if state == 'audio':
            self.nextButton.setText(self.tr("Finish"))
        else: self.nextButton.setText(self.tr("Next"))
    
    def finish(self):
        """Write config file, close the install tool and start Maestro."""
        # Write config values
        config.shutdown()
        logger.info("Install tool finished. Ready to start Maestro.")
        from maestro.application import executeEntryPoint
        executeEntryPoint('maestro')
    
    def _handlePrevButton(self):
        """Handle the previous button."""
        if self.state not in ['language', 'database']:
            index = self.states.index(self.state) - 1
            while self._shouldSkip(self.states[index]):
                index -= 1
            self.showState(self.states[index])
            if self.state == 'database':
                # Close the database connection when returning to database settings
                db.shutdown()
        
    def _handleNextButton(self):
        """Handle the next button: Call finish on the current SettingsWidget, decide which state is next
        (this may depend on the configuration) and switch to it."""
        if not self.stateWidgets[self.state].finish():
            return
        
        index = self.states.index(self.state) + 1
        while index < len(self.states) and self._shouldSkip(self.states[index]):
            index += 1
        
        if index < len(self.states):
            self.showState(self.states[index])
        else: self.finish()
        
    def _shouldSkip(self, state):
        """Some states should be skipped, when the database already contains the corresponding values."""
        if state == 'domains':
            return db.query("SELECT COUNT(*) FROM {p}domains").getSingle() > 0
        elif state == 'tags':
            return db.query("SELECT COUNT(*) FROM {p}tagids").getSingle() > 0
        else: return False
        

class SettingsWidget(QtGui.QWidget):
    """This is the abstract base class for all pages/steps/slides of the InstallTool. It simply contains
    a title label and a QVBoxLayout. *installTool* is a reference to the InstallToolWindow, *titleNumber*
    is the step number displayed in the title (the actual title is set by the subclasses using setTitle).
    """
    def __init__(self, installTool, titleNumber):
        super().__init__()
        layout = QtGui.QVBoxLayout(self)
        self.installTool = installTool
        self.titleNumber = titleNumber
        
        self.titleLabel = QtGui.QLabel()
        self.titleLabel.setStyleSheet('QLabel {font-size: 16px; font-weight: bold}')
        layout.addWidget(self.titleLabel)
        
        self.textLabel = QtGui.QLabel()
        self.textLabel.setWordWrap(True)
        layout.addWidget(self.textLabel)
        
    def setTitle(self, title):
        """Set the title displayed in the title label."""
        self.titleLabel.setText("{}. {}".format(self.titleNumber, title))
        
    def setText(self, text):
        self.textLabel.setText(text)
        
    def finish(self):
        """Check the settings in this widget. If they are ok, do necessary actions (like updating config
        variables, establishing a db connection...) and if that works, return True. Otherwise display an
        error message and return False.
        """
        return True
        
        
class LanguageWidget(SettingsWidget):
    """Widget to choose the language (locale would be more appropriate)."""
    def __init__(self, installTool, titleNumber):
        super().__init__(installTool, titleNumber)
        self.setTitle(self.tr("Language"))
        formLayout = QtGui.QFormLayout()
        self.layout().addLayout(formLayout)
        self.layout().addStretch()
        
        self.languageBox = QtGui.QComboBox()
        self.languageBox.addItem("English", "en")
        self.languageBox.addItem("Deutsch", "de")
        locale = QtCore.QLocale.system().name()
        if locale == 'de' or locale.startswith('de_'):
            self.languageBox.setCurrentIndex(1)
        formLayout.addRow(self.tr("Please choose a language: "), self.languageBox)
        
    def finish(self):
        """Set the locale and update InstallToolWidget to the new language."""
        config.options.i18n.locale = self.languageBox.itemData(self.languageBox.currentIndex())
        loadTranslators(app, logger)
        # Update the texts which already have been translated
        self.installTool.nextButton.setText(self.tr("Next"))
        self.installTool.prevButton.setText(self.tr("Previous"))
        self.installTool.setWindowTitle(self.tr("Maestro Install Tool"))
        self.installTool.createOtherWidgets()
        return True

               
class DatabaseWidget(SettingsWidget):
    def __init__(self, installTool, titleNumber):
        super().__init__(installTool, titleNumber)
        self.setTitle(self.tr("Database settings"))
        self.setText(self.tr("Choose a database type and enter the necessary connection parameters."))
        groupBox = QtGui.QGroupBox(self.tr("Database type"))
        layout = QtGui.QVBoxLayout(groupBox)
        self.sqliteButton = QtGui.QRadioButton(self.tr("SQLite"))
        self.sqliteButton.setChecked(True)
        self.sqliteButton.toggled.connect(self._handleTypeButton)
        layout.addWidget(self.sqliteButton)
        self.mysqlButton = QtGui.QRadioButton(self.tr("MySQL"))
        self.mysqlButton.toggled.connect(self._handleTypeButton)
        layout.addWidget(self.mysqlButton)
        self.layout().addWidget(groupBox)
        
        groupBox = QtGui.QGroupBox(self.tr("Connection settings"))
        self.stackedLayout = QtGui.QStackedLayout(groupBox)
        self.layout().addWidget(groupBox)
        
        flexConfig = flexform.FlexFormConfig()
        flexConfig.addField('path', self.tr("Database file"), 'path',
                            dialogTitle=self.tr("Choose database file"),
                            default=config.options.database.sqlite_path)
        flexConfig.addField('prefix', self.tr("Table prefix (optional)"), 'string',
                            default=config.options.database.prefix)
        self.sqliteFlexForm = flexform.FlexForm(flexConfig, self)
        self.stackedLayout.addWidget(self.sqliteFlexForm)
        
        flexConfig = flexform.FlexFormConfig()
        flexConfig.addField('name', self.tr("Database name"), 'string',
                            default=config.options.database.name)
        flexConfig.addField('user', self.tr("User name"), 'string',
                            default=config.options.database.user)
        flexConfig.addField('password', self.tr("Password"), 'password',
                            default=config.options.database.password)
        flexConfig.addField('host', self.tr("Host"), 'string',
                            default=config.options.database.host)
        flexConfig.addField('port', self.tr("Port (optional)"), 'integer',
                            default=config.options.database.port)
        flexConfig.addField('prefix', self.tr("Table prefix (optional)"), 'string',
                            default=config.options.database.prefix)
        self.mysqlFlexForm = flexform.FlexForm(flexConfig)
        self.stackedLayout.addWidget(self.mysqlFlexForm)
        
    def _handleTypeButton(self):
        if self.sqliteButton.isChecked():
            self.stackedLayout.setCurrentIndex(0)
        else: self.stackedLayout.setCurrentIndex(1)
        
    def finish(self):
        """Store user input in config variables and establish a connection. If the database is empty, create
        tables. If it is not empty check whether tagids-table exist. If anything goes wrong, display an
        error and close the connection again.
        """
        if self.sqliteButton.isChecked():
            config.options.database.type = 'sqlite'
            config.options.database.sqlite_path = self.sqliteFlexForm.getValue('path')
            config.options.database.prefix = self.sqliteFlexForm.getValue('prefix')
        else:
            config.options.database.type = 'mysql'
            config.options.database.name = self.mysqlFlexForm.getValue('name')
            config.options.database.user = self.mysqlFlexForm.getValue('user')
            config.options.database.password = self.mysqlFlexForm.getValue('password')
            config.options.database.host = self.mysqlFlexForm.getValue('host')
            config.options.database.port = self.mysqlFlexForm.getValue('port')
            config.options.database.prefix = self.mysqlFlexForm.getValue('prefix')
            
        # Check database access and if necessary create tables
        try:
            db.init()
        except db.DBException as e:
            logger.error("I cannot connect to the database. SQL error: {}".format(e.message))
            QtGui.QMessageBox.warning(self, self.tr("Database connection failed"),
                                      self.tr("I cannot connect to the database."))
            return False 
        
        from .database import tables
        if all(table.exists() for table in tables.tables.values()):
            return True
        
        if len(db.listTables()) > 0: # otherwise we assume a new installation and create all tables
            buttons = QtGui.QMessageBox.Yes | QtGui.QMessageBox.No | QtGui.QMessageBox.Abort
            if not any(table.exists() for table in tables.tables): 
                if QtGui.QMessageBox.question(self, self.tr("Database tables missing"),
                        self.tr("Although the database is not empty, I cannot find any of my tables. If you "
                                "use a table prefix, please check whether it is correct. Shall I continue "
                                "and create the missing tables?"),
                          buttons, QtGui.QMessageBox.Yes) != QtGui.QMessageBox.Yes:
                    db.close()
                    return False
            else:
                missingTables = [table.name for table in tables.tables if not table.exists()]
                if QtGui.QMessageBox.question(self, self.tr("Database table(s) missing"),
                          self.tr("Some tables are missing: {}. Shall I continue and create them?")
                                    .format(', '.join(missingTables)),
                          buttons, QtGui.QMessageBox.Yes) != QtGui.QMessageBox.Yes:
                    db.close()
                    return False
        
        try:
            database.createTables()
        except db.DBException as e:
            logger.error("I cannot create database tables. SQL error: {}".format(e.message))
            QtGui.QMessageBox.warning(self, self.tr("Cannot create tables"),
                                      self.tr("I cannot create the database tables. Please make sure that "
                                              "the specified user has the necessary permissions."))
            db.close()
            return False 
        return True
    
        
class DomainWidget(SettingsWidget):
    """Let the user create at least one domain. Also create one source for each domain."""
    def __init__(self, installTool, titleNumber):
        super().__init__(installTool, titleNumber)
        self.setTitle(self.tr("Domain settings"))
        self.setText(self.tr(
            "Maestro separates different types of media into domains like \"Music\", \"Movies\".\n"
            "Enable / create one or more domains that you want to use."
            ))
        
        self.domainManager = flexform.FlexTable(self)
        model = flexform.FlexTableTupleModel(parent=self)
        model.addField('enabled', self.tr("Enabled"), 'check')
        model.addField('name', self.tr("Name"), 'string')
        model.addField('path', self.tr("Path"), 'path',
                       dialogTitle = self.tr("Choose source directory"),
                       pathType = 'existingDirectory')
        self.domainManager.setModel(model)
        newDomainAction = QtGui.QAction(QtGui.QIcon.fromTheme('list-add'), self.tr("Add domain"), self)
        newDomainAction.triggered.connect(self._addDomain)
        self.domainManager.addAction(newDomainAction)
        removeDomainAction = QtGui.QAction(QtGui.QIcon.fromTheme('list-remove'), self.tr("Remove domain"), self)
        removeDomainAction.triggered.connect(self._removeDomain)
        self.domainManager.addAction(removeDomainAction)
        
        self.layout().addWidget(self.domainManager)
        self.layout().addStretch()
        
        # Note: The domain widget is only displayed, if no domain exists in the database
        self._addDomain(True, self.tr("Music"), os.path.expanduser(self.tr('~/Music')))
        self._addDomain(False, self.tr("Movies"), os.path.expanduser(self.tr('~/Movies')))
        self._addDomain(False, self.tr("Documents"), os.path.expanduser(self.tr('~/Documents')))

    def _addDomain(self, enabled=True, title=None, path=''):
        if title is None:
            title = self.tr("New domain")
        newDomain = [enabled, title, path]
        self.domainManager.model.addItem(newDomain)
        
    def _removeDomain(self):
        domains = self.domainManager.selectedItems()
        if len(domains) == 1:
            self.domainManager.model.removeItem(domains[0])
            
    def finish(self):
        items = [item for item in self.domainManager.model.items if item[0]] # enabled items
        if len(items) == 0:
            QtGui.QMessageBox.warning(self, self.tr("No domain"),
                                      self.tr("Please create and activate at least one domain."))
            return False
        if any(len(set(item[i] for item in items)) < len(items) for i in (1,2)):
            QtGui.QMessageBox.warning(self, self.tr("Names not unique"),
                                      self.tr("Please give each domain a unique name and path."))
            return False
        
        db.multiQuery("INSERT INTO {p}domains (name) VALUES (?)", [(item[1],) for item in items])
        
        # Create one source for each domain
        config.storage.filesystem.sources = [
                {'name': item[1], 'path': item[2], 'domain': item[0], 'enabled': True}
                for item in items
            ]
                                             
        return True
         
    
class TagWidget(SettingsWidget):
    """This widgets, which is a much simplified version of the TagManager, allows the user to define the
    initial tagtypes. It is only shown when the tagids table is empty.
    """ 
    def __init__(self, installTool, titleNumber):
        super().__init__(installTool, titleNumber)
        self.setTitle(self.tr("Tag settings (optional)"))
        self.setText(self.tr("Uncheck tags that you do not want to be created. "
                             "The first two tags play a special role: "
                             "They are used for songtitles and albumtitles. "
                             "Do not change their names unless you really know what you do!"))
        
        self.columns = [
                ("name",    self.tr("Name")),
                ("type",    self.tr("Value-Type")),
                ("title",   self.tr("Title")),
                ("icon",    self.tr("Icon")),
                ("private", self.tr("Private?")),
                ]
        
        self.tableWidget = QtGui.QTableWidget()
        self.tableWidget.setColumnCount(len(self.columns))
        self.tableWidget.setHorizontalHeaderLabels([column[1] for column in self.columns])
        self.tableWidget.verticalHeader().hide()
        self.tableWidget.horizontalHeader().setResizeMode(QtGui.QHeaderView.ResizeToContents)
        self.layout().addWidget(self.tableWidget)
        
        buttonBarLayout = QtGui.QHBoxLayout()
        self.layout().addLayout(buttonBarLayout)
        addButton = QtGui.QPushButton(self.tr("Add tag"))
        addButton.setIcon(QtGui.QIcon.fromTheme('list-add'))
        addButton.clicked.connect(self._handleAddButton)
        buttonBarLayout.addWidget(addButton)
        buttonBarLayout.addStretch()
        
        tagList = [
                ('title', 'varchar', self.tr("Title")),
                ('album', 'varchar', self.tr("Album")),
                ('composer', 'varchar', self.tr("Composer")),
                ('artist', 'varchar', self.tr("Artist")),
                ('performer', 'varchar', self.tr("Performer")),
                ('conductor', 'varchar', self.tr("Conductor")),
                ('genre', 'varchar', self.tr("Genre")),
                ('date', 'date', self.tr("Date")),
                ('comment', 'text', self.tr("Comment")),
        ]
        self.tableWidget.setRowCount(len(tagList))
        for row, data in enumerate(tagList):
            self._addTag(row, *data)
        
    def _addTag(self, row, name, valueType, title):
        """Create items/widgets for a new tagtype in row *row* of the QTableWidget. *name*, *valueType* and
        *title* are attributes of the new tagtype."""
        self.tableWidget.setRowHeight(row, 36) # Enough space for icons
        
        column = self._getColumnIndex('name')
        item = QtGui.QTableWidgetItem(name)
        if row <= 1:
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsEditable)
        else: item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsEditable | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        self.tableWidget.setItem(row, column, item)
        
        column = self._getColumnIndex('type')
        if row <= 1:
            item = QtGui.QTableWidgetItem('varchar')
            item.setFlags(Qt.ItemIsEnabled)
            self.tableWidget.setItem(row, column, item)
        else:
            box = QtGui.QComboBox()
            types = ['varchar', 'text', 'date']
            box.addItems(types)
            box.setCurrentIndex(types.index(valueType))
            self.tableWidget.setIndexWidget(self.tableWidget.model().index(row, column), box)
        
        column = self._getColumnIndex('title')
        item = QtGui.QTableWidgetItem(title)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsEditable)
        self.tableWidget.setItem(row, column, item)
        
        column = self._getColumnIndex('icon')
        label = IconLabel(':maestro/tags/{}.png'.format(name))
        self.tableWidget.setIndexWidget(self.tableWidget.model().index(row, column), label)
        
        column = self._getColumnIndex('private')
        item = QtGui.QTableWidgetItem()
        if row <= 1:
            item.setFlags(Qt.ItemIsEnabled) # Insert an empty item that is not editable
        else:
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
        self.tableWidget.setItem(row, column, item)
    
    def finish(self):
        """Read tag information from table, check it (invalid or duplicate tag names?) and write it to the
        tagids table."""
        # Read tags
        tags = collections.OrderedDict()
        for row in range(self.tableWidget.rowCount()):
            column = self._getColumnIndex('name')
            if self.tableWidget.item(row, column).checkState() != Qt.Checked:
                continue
            name = self.tableWidget.item(row, column).text()
            
            # Check invalid tag names
            if not isValidTagName(name):
                QtGui.QMessageBox.warning(self, self.tr("Invalid tagname"),
                                          self.tr("'{}' is not a valid tagname.").format(name))
                return False
            
            # Check duplicate tag names
            if name in tags:
                QtGui.QMessageBox.warning(self, self.tr("Some tags have the same name"),
                                          self.tr("There is more than one tag with name '{}'.").format(name))
                return False
                
            column = self._getColumnIndex('type')
            if row <= 1:
                valueType = self.tableWidget.item(row, column).text()
            else: valueType = self.tableWidget.indexWidget(
                                                self.tableWidget.model().index(row, column)).currentText()
            
            column = self._getColumnIndex('title')
            title = self.tableWidget.item(row, column).text()
            if title == '':
                title = None
                
            column = self._getColumnIndex('icon')
            iconLabel = self.tableWidget.indexWidget(self.tableWidget.model().index(row, column))
            icon = iconLabel.path
            
            column = self._getColumnIndex('private')
            private = self.tableWidget.item(row, column).checkState() == Qt.Checked
            tags[name] = (name, valueType, title, icon, 1 if private else 0, row+1)
        
        # Write tags to database
        assert db.query("SELECT COUNT(*) FROM {}tagids".format(db.prefix)).getSingle() == 0
        db.multiQuery("INSERT INTO {}tagids (tagname, tagtype, title, icon, private, sort)"
                      " VALUES (?,?,?,?,?,?)"
                      .format(db.prefix), tags.values())
        
        # The first two tags are used as title and album. popitem returns a (key, value) tuple.
        config.options.tags.title_tag = tags.popitem(last=False)[0]
        config.options.tags.album_tag = tags.popitem(last=False)[0] 
        return True
        
    def _handleAddButton(self):
        """Add a new line/tagtype to the table."""
        rowCount = self.tableWidget.rowCount()
        self.tableWidget.setRowCount(rowCount+1)
        self._addTag(rowCount, '', 'varchar', '')
        # Scroll to last line
        self.tableWidget.scrollTo(self.tableWidget.model().index(rowCount, 0))
        
    def _getColumnIndex(self, columnKey):
        """Return the index of the column with the given key (i.e. the first part of the corresponding tuple
        in self.columns."""
        for i in range(len(self.columns)):
            if self.columns[i][0] == columnKey:
                return i
        raise ValueError("Invalid key {}".format(columnKey))
        

class AudioWidget(SettingsWidget):
    """Check which audio backend plugins are available (i.e. the third-party library can be imported) and
    let the user choose one or more."""
    def __init__(self, installTool, titleNumber):
        super().__init__(installTool, titleNumber)
        self.setTitle(self.tr("Audio settings"))
        self.setText(self.tr(
            "Maestro can play music using various backends. All of them require third-party libraries "
            "to be installed and a plugin to be enabled. "
            "Please choose the backends that you want to enable."))
        
        audioBackendFound = False
        try:
            from PyQt4.phonon import Phonon
            self.phononBox = QtGui.QCheckBox(self.tr("Phonon"))
            self.phononBox.setChecked(True)
            audioBackendFound = True
        except ImportError:
            self.phononBox = QtGui.QCheckBox(self.tr("Phonon (cannot find PyQt4.phonon)"))
            self.phononBox.setEnabled(False)
        self.layout().addWidget(self.phononBox)
        try:
            import mpd
            self.mpdBox = QtGui.QCheckBox(self.tr("MPD"))
            self.mpdBox.setChecked(True)
            audioBackendFound = True
        except ImportError:
            self.mpdBox = QtGui.QCheckBox(self.tr("MPD (cannot find python-mpd2)"))
            self.mpdBox.setEnabled(False)
        self.layout().addWidget(self.mpdBox)
        if not audioBackendFound:
            noBackendBox = QtGui.QRadioButton(self.tr("No backend"))
            noBackendBox.setChecked(True)
            self.layout().addWidget(noBackendBox)
            label = QtGui.QLabel(self.tr(
                "You will not be able to play music. Please install one of the missing packages. "
                "If you continue, you will also need to enable the corresponding plugin in the preferences."
                ))
            label.setWordWrap(True)
            self.layout().addWidget(label)
        
        self.layout().addStretch()
        
    def finish(self):
        """Store user input in config variables."""
        if self.phononBox.isChecked() and "phonon" not in config.options.main.plugins:
            config.options.main.plugins.append("phonon")
        elif self.mpdBox.isChecked() and "mpd" not in config.options.main.plugins:
            config.options.main.plugins.append("mpd")
        return True
        
        
def getIcon(name):
    """Return a QIcon for the icon with the given name."""
    return QtGui.QIcon(":maestro/icons/" + name)


class IconLabel(QtGui.QLabel):
    """Label for the icon column in TagWidget. It displays the icon and provides a contextmenu to change
    or remove it.
    """
    def __init__(self, path):
        super().__init__()
        self.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.setPath(path)
        
    def setPath(self, path):
        """Set the icon path."""
        pixmap = QtGui.QPixmap()
        if path is not None and pixmap.load(path):
            pixmap = pixmap.scaled(32, 32, transformMode=Qt.SmoothTransformation)
        self.path = path
        self.setPixmap(pixmap)
                
    def contextMenuEvent(self, event):
        menu = QtGui.QMenu(self)
        if self.path is None:
            changeAction = QtGui.QAction(self.tr("Add icon..."), menu)
        else:changeAction = QtGui.QAction(self.tr("Change icon..."), menu)
        changeAction.triggered.connect(lambda: self.mouseDoubleClickEvent(None))
        menu.addAction(changeAction)
        
        removeAction = QtGui.QAction(self.tr("Remove icon"), menu)
        removeAction.setEnabled(self.path is not None)
        removeAction.triggered.connect(lambda: self.setPath(None))
        menu.addAction(removeAction)
        menu.exec_(event.globalPos())
        
    def mouseDoubleClickEvent(self, event):
        from maestro.gui.misc import iconchooser
        result = iconchooser.IconChooser.getIcon([':maestro/tags'], self)
        if result:
            self.setPath(result[1])

def run():
    """Run the install tool."""
    global app
    app = QtGui.QApplication([])
    from maestro import resources
    widget = InstallToolWindow()
    widget.show()
    app.exec_()
    
if __name__ == "__main__":
    run()
