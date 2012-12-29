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

"""
The InstallTool is opened when an important config variable is missing, when the database connection fails
and in similar cases. It contains several pages of configuration widgets. When enough information is
collected it will connect to the database and create the tables (if the database is empty) and fill them with
initial tags (in particular the special tags title and album).

Currently the order of pages is:

1. Language
2. General settings (in particular database type)
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
from omg import config, logging, database as db
from omg.application import loadTranslators
from omg.core.tags import isValidTagName
from omg.gui.misc import iconchooser

logger = logging.getLogger("Install tool")


class InstallToolWindow(QtGui.QWidget):
    """The InstallToolWindow contains several pages/states/SettingsWidgets which allow the user to define
    basic config variables and set up the database.
    
    The order in which the states are displayed may depend on the configuration (e.g. only one of sqlite or
    mysql is shown) and is figured out in _handleNextButton.
    """
    # List of all states/pages
    states = ['language','general','sqlite','mysql','tags','specialtags']
    # Mapping state name to the corresponding SettingsWidget
    stateWidgets = {}
    # Current state
    state = 'language'
    
    def __init__(self):
        super().__init__()
        
        config.init()
        logging.init()
        
        loadTranslators(app,logger)
        self.setWindowTitle(self.tr("OMG Install Tool"))
        self.resize(630,550)
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
        
        self.stateWidgets['language'] = LanguageWidget(self,1)
        self.stackedLayout.addWidget(self.stateWidgets['language'])
        # All other widgets are not created until the language is chosen
        
    def createOtherWidgets(self):
        """Create all settings widgets except for the language widget."""
        self.stateWidgets['general'] = GeneralSettingsWidget(self,2)
        self.stackedLayout.addWidget(self.stateWidgets['general'])
        
        self.stateWidgets['sqlite'] = SQLiteWidget(self,3)
        self.stackedLayout.addWidget(self.stateWidgets['sqlite'])
        
        self.stateWidgets['mysql'] = MySQLWidget(self,3)
        self.stackedLayout.addWidget(self.stateWidgets['mysql'])
        
        self.stateWidgets['tags'] = TagWidget(self,4)
        self.stackedLayout.addWidget(self.stateWidgets['tags'])
        
        self.stateWidgets['specialtags'] = SpecialTagsWidget(self,4)
        self.stackedLayout.addWidget(self.stateWidgets['specialtags'])
    
    def showState(self,state):
        """Display the settingsWidget for the given state (from the list self.states)."""
        self.state = state
        self.stackedLayout.setCurrentWidget(self.stateWidgets[state])
        self.prevButton.setEnabled(self.state not in ['language','general'])
        if state in ['tags','specialtags']:
            self.nextButton.setText(self.tr("Finish"))
        else: self.nextButton.setText(self.tr("Next"))
    
    def finish(self):
        """Write config file, close the install tool and start OMG."""
        # Write config values
        config.shutdown()
        logger.info("Install tool finished. Ready to start OMG.")
        from omg.application import executeEntryPoint
        executeEntryPoint('omg')
    
    def _handlePrevButton(self):
        """Handle the previous button."""
        if self.state in ['sqlite','mysql']:
            self.showState('general')
        elif self.state in ['tags','specialtags']:
            # Close the database connection when returning to database settings
            db.close()
            if self.stateWidgets['general'].sqliteBox.isChecked():
                self.showState('sqlite')
            else: self.showState('mysql')
        
    def _handleNextButton(self):
        """Handle the next button: Call finish on the current SettingsWidget, decide which state is next
        (this may depend on the configuration) and switch to it."""
        ok = self.stateWidgets[self.state].finish()
        if not ok:
            return
        
        if self.state == 'language':
            self.showState('general')
        elif self.state == 'general':
            if self.stateWidgets['general'].sqliteBox.isChecked():
                self.showState('sqlite')
            else: self.showState('mysql')
        elif self.state in ['sqlite','mysql']:
            # Database connection is established in 'finish' above
            tags = list(db.query("SELECT tagname FROM {}tagids".format(db.prefix)).getSingleColumn())
            if len(tags) == 0:
                # No tags exist. This is the case when installing OMG
                self.showState('tags')
            else:
                # This is the case when the config file was deleted
                if config.options.tags.title_tag not in tags or config.options.tags.album_tag not in tags:
                    self.showState('specialtags')
                else: self.finish()
        else:
            self.finish()
        

class SettingsWidget(QtGui.QWidget):
    """This is the abstract base class for all pages/steps/slides of the InstallTool. It simply contains
    a title label and a QVBoxLayout. *installTool* is a reference to the InstallToolWindow, *titleNumber*
    is the step number displayed in the title (the actual title is set by the subclasses using setTitle).
    """
    def __init__(self,installTool,titleNumber):
        super().__init__()
        layout = QtGui.QVBoxLayout(self)
        self.installTool = installTool
        self.titleNumber = titleNumber
        
        self.titleLabel = QtGui.QLabel()
        self.titleLabel.setStyleSheet('QLabel {font-size: 16px; font-weight: bold}')
        layout.addWidget(self.titleLabel)
        
    def setTitle(self,title):
        """Set the title displayed in the title label."""
        self.titleLabel.setText("{}. {}".format(self.titleNumber,title))
        
    def finish(self):
        """Check the settings in this widget. If they are ok, do necessary actions (like updating config
        variables, establishing a db connection...) and if that works, return True. Otherwise display an
        error message and return False.
        """
        return True
        
        
class LanguageWidget(SettingsWidget):
    """Widget to choose the language (locale would be more appropriate)."""
    def __init__(self,installTool,titleNumber):
        super().__init__(installTool,titleNumber)
        self.setTitle(self.tr("Language"))
        formLayout = QtGui.QFormLayout()
        self.layout().addLayout(formLayout)
        self.layout().addStretch()
        
        self.languageBox = QtGui.QComboBox()
        self.languageBox.addItem("English","en")
        self.languageBox.addItem("Deutsch","de")
        locale = QtCore.QLocale.system().name()
        if locale == 'de' or locale.startswith('de_'):
            self.languageBox.setCurrentIndex(1)
        formLayout.addRow(self.tr("Please choose a language: "),self.languageBox)
        
    def finish(self):
        """Set the locale and update InstallToolWidget to the new language."""
        config.options.i18n.locale = self.languageBox.itemData(self.languageBox.currentIndex())
        loadTranslators(app,logger)
        # Update the texts which already have been translated
        self.installTool.nextButton.setText(self.tr("Next"))
        self.installTool.prevButton.setText(self.tr("Previous"))
        self.installTool.setWindowTitle(self.tr("OMG Install Tool"))
        self.installTool.createOtherWidgets()
        return True


class GeneralSettingsWidget(SettingsWidget):
    """General settings include the collection directory, the database type and the audio backend type."""
    def __init__(self,installTool,titleNumber):
        super().__init__(installTool,titleNumber)
        self.setTitle(self.tr("General settings"))
        formLayout = QtGui.QFormLayout()
        self.layout().addLayout(formLayout)
        self.layout().addStretch()
        
        collectionLayout = QtGui.QHBoxLayout()
        self.collectionLineEdit = QtGui.QLineEdit(config.options.main.collection)
        collectionLayout.addWidget(self.collectionLineEdit)
        fileChooserButton = QtGui.QPushButton()
        fileChooserButton.setIcon(QtGui.QApplication.style().standardIcon(QtGui.QStyle.SP_DirIcon))
        fileChooserButton.clicked.connect(self._handleFileChooserButton)
        collectionLayout.addWidget(fileChooserButton)
        formLayout.addRow(self.tr("Music directory"),collectionLayout)
        
        dbChooserLayout = QtGui.QVBoxLayout()
        dbButtonGroup = QtGui.QButtonGroup()
        self.sqliteBox = QtGui.QRadioButton("SQLite")
        dbButtonGroup.addButton(self.sqliteBox)
        self.sqliteBox.setChecked(config.options.database.type == 'sqlite')
        self.mysqlBox = QtGui.QRadioButton("MySQL")
        dbButtonGroup.addButton(self.mysqlBox)
        self.sqliteBox.setChecked(config.options.database.type == 'mysql')
        dbChooserLayout.addWidget(self.sqliteBox)
        dbChooserLayout.addWidget(self.mysqlBox)
        dbButtonGroup.addButton(self.sqliteBox)
        dbButtonGroup.addButton(self.mysqlBox)
        formLayout.addRow(self.tr("Database type"),dbChooserLayout)
        
        audioBackendLayout = QtGui.QVBoxLayout()
        audioBackendFound = False
        try:
            from PyQt4.phonon import Phonon
            self.phononBox = QtGui.QRadioButton(self.tr("Phonon"))
            self.phononBox.setChecked(True)
            audioBackendFound = True
        except ImportError:
            self.phononBox = QtGui.QRadioButton(self.tr("Phonon (cannot find PyQt4.phonon)"))
            self.phononBox.setEnabled(False)
        audioBackendLayout.addWidget(self.phononBox)
        try:
            import mpd
            self.mpdBox = QtGui.QRadioButton(self.tr("MPD"))
            self.mpdBox.setChecked(not audioBackendFound) # not if Phonon is already checked
            audioBackendFound = True
        except ImportError:
            self.mpdBox = QtGui.QRadioButton(self.tr("MPD (cannot find python-mpd2)"))
            self.mpdBox.setEnabled(False)
        audioBackendLayout.addWidget(self.mpdBox)
        if not audioBackendFound:
            noBackendBox = QtGui.QRadioButton(self.tr("No backend (to choose a backend later, enable the corresponding plugin)."))
            audioBackendLayout.addWidget(noBackendBox)
        formLayout.addRow(self.tr("Audio backend"),audioBackendLayout)
        
    def finish(self):
        """Store user input in config variables."""
        if self.collectionLineEdit.text():
            config.options.main.collection = self.collectionLineEdit.text()
            config.options.database.type = 'mysql' if self.mysqlBox.isChecked() else 'sqlite'
        else:
            QtGui.QMessageBox.warning(self,self.tr("No music directory"),
                                      self.tr("You must choose a directory for your music collection."))
            return False
        if self.phononBox.isChecked() and "phonon" not in config.options.main.plugins:
            config.options.main.plugins.append("phonon")
        elif self.mpdBox.isChecked() and "mpd" not in config.options.main.plugins:
            config.options.main.plugins.append("mpd")
        return True
    
    def _handleFileChooserButton(self):
        """Handle the button next to the collection directory field: Open a file dialog."""
        result = QtGui.QFileDialog.getExistingDirectory(self,self.tr("Choose music collection directory"),
                                                        self.collectionLineEdit.text())
        if result:
            self.collectionLineEdit.setText(result)
                

class DBSettingsWidget(SettingsWidget):
    """Superclass for SQLiteWidget and MySQLWidget."""
    def finish(self):
        """Store user input in config variables and establish a connection. If the database is empty, create
        tables. If it is not empty check whether tagids-table exist. If anything goes wrong, display an
        error and close the connection again.
        """
        # Check database access and if necessary create tables
        try:
            db.connect()
        except db.sql.DBException as e:
            logger.error("I cannot connect to the database. SQL error: {}".format(e.message))
            QtGui.QMessageBox.warning(self,self.tr("Database connection failed"),
                                      self.tr("I cannot connect to the database."))
            return False 
        
        from .database import tables
        if all(table.exists() for table in tables.tables):
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
            db.createTables(ignoreExisting=True)
        except db.sql.DBException as e:
            logger.error("I cannot create database tables. SQL error: {}".format(e.message))
            QtGui.QMessageBox.warning(self,self.tr("Cannot create tables"),
                                      self.tr("I cannot create the database tables. Please make sure that "
                                              "the specified user has the necessary permissions."))
            db.close()
            return False 
        return True
    
    
class SQLiteWidget(DBSettingsWidget):
    """Settings for SQLite (mainly the path to the database file)."""
    def __init__(self,installTool,titleNumber):
        super().__init__(installTool,titleNumber)
        self.setTitle(self.tr("SQLite settings"))
        
        label = QtGui.QLabel(self.tr(
            "Choose an existing SQLite database file or enter a path where a new database should be created. "
            "Use the prefix 'config:' to specify a path relative the configuration directory."))
        label.setWordWrap(True)
        self.layout().addWidget(label)
        
        formLayout = QtGui.QFormLayout()
        self.layout().addLayout(formLayout)
        
        pathLayout = QtGui.QHBoxLayout()
        self.pathLineEdit = QtGui.QLineEdit(config.options.database.sqlite_path)
        pathLayout.addWidget(self.pathLineEdit)
        fileChooserButton = QtGui.QPushButton()
        fileChooserButton.setIcon(QtGui.QApplication.style().standardIcon(QtGui.QStyle.SP_DirIcon))
        fileChooserButton.clicked.connect(self._handleFileChooserButton)
        pathLayout.addWidget(fileChooserButton)
        formLayout.addRow(self.tr("Database file"),pathLayout)
        
        self.layout().addStretch()
        
    def _handleFileChooserButton(self):
        """Handle the button next to the collection directory field: Open a file dialog."""
        # Replace config: prefix before opening the dialog
        path = config.options.database.sqlite_path.strip()
        if path.startswith('config:'):
            path = os.path.join(config.CONFDIR,path[len('config:'):])
        result = QtGui.QFileDialog.getSaveFileName(self,self.tr("Choose database file"),path)
        if result:
            self.pathLineEdit.setText(result)
    
    def finish(self):
        config.options.database.sqlite_path = self.pathLineEdit.text()
        return super().finish()


class MySQLWidget(DBSettingsWidget):
    """Settings for SQL (database name, user etc.)"""
    def __init__(self,installTool,titleNumber):
        super().__init__(installTool,titleNumber)
        self.setTitle(self.tr("MySQL settings"))
        
        label = QtGui.QLabel(self.tr("Please create an empty database for OMG."
                                     " The password will be stored as plain text."))
        label.setWordWrap(True)
        self.layout().addWidget(label)
        
        formLayout = QtGui.QFormLayout()
        self.layout().addLayout(formLayout)
        self.layout().addStretch()
        
        self.dbNameLineEdit = QtGui.QLineEdit(config.options.database.mysql_db)
        formLayout.addRow(self.tr("Database name"),self.dbNameLineEdit)
        self.dbUserLineEdit = QtGui.QLineEdit(config.options.database.mysql_user)
        formLayout.addRow(self.tr("Database user"),self.dbUserLineEdit)
        passwordLayout = QtGui.QVBoxLayout()
        self.dbPasswordLineEdit = QtGui.QLineEdit(config.options.database.mysql_password)
        self.dbPasswordLineEdit.setEchoMode(QtGui.QLineEdit.Password)
        passwordLayout.addWidget(self.dbPasswordLineEdit)
        echoModeBox = QtGui.QCheckBox('Show password')
        echoModeBox.clicked.connect(lambda checked: self.dbPasswordLineEdit.setEchoMode(
                                    QtGui.QLineEdit.Normal if checked else QtGui.QLineEdit.Password))
        passwordLayout.addWidget(echoModeBox)
        formLayout.addRow(self.tr("Database password"),passwordLayout)
        self.dbHostLineEdit = QtGui.QLineEdit(config.options.database.mysql_host)
        formLayout.addRow(self.tr("Database host"),self.dbHostLineEdit)
        self.dbPortLineEdit = QtGui.QLineEdit(str(config.options.database.mysql_port))
        formLayout.addRow(self.tr("Database port"),self.dbPortLineEdit)
        self.dbPrefixLineEdit = QtGui.QLineEdit(str(config.options.database.prefix))
        formLayout.addRow(self.tr("Table prefix (optional)"),self.dbPrefixLineEdit)
    
    def finish(self):
        config.options.database.mysql_db = self.dbNameLineEdit.text()
        config.options.database.mysql_user = self.dbUserLineEdit.text()
        config.options.database.mysql_password = self.dbPasswordLineEdit.text()
        config.options.database.mysql_host = self.dbHostLineEdit.text()
        try:
            config.options.database.mysql_port = int(self.dbPortLineEdit.text())
        except ValueError:
            QtGui.QMessageBox.warning(self,self.tr("Invalid port"),
                                      self.tr("Please enter a correct port number."))
            return False
        config.options.database.prefix = self.dbPrefixLineEdit.text()
            
        return super().finish()
        
    
class TagWidget(SettingsWidget):
    """This widgets, which is a much simplified version of the TagManager, allows the user to define the
    initial tagtypes. It is only shown when the tagids table is empty.
    """ 
    def __init__(self,installTool,titleNumber):
        super().__init__(installTool,titleNumber)
        self.setTitle(self.tr("Tag settings (optional)"))
        label = QtGui.QLabel(self.tr("Uncheck tags that you do not want to be created. "
                                     "The first two tags play a special role: "
                                     "They are used for songtitles and albumtitles. "
                                     "Do not change their names unless you really know what you do!"))
        label.setWordWrap(True)
        self.layout().addWidget(label)
        
        self.columns = [
                ("name",   self.tr("Name")),
                ("type",   self.tr("Value-Type")),
                ("title",  self.tr("Title")),
                ("icon",   self.tr("Icon")),
                ("private",self.tr("Private?")),
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
        addButton.setIcon(getIcon('add.png'))
        addButton.clicked.connect(self._handleAddButton)
        buttonBarLayout.addWidget(addButton)
        buttonBarLayout.addStretch()
        
        tagList = [
                ('title','varchar',self.tr("Title")),
                ('album','varchar',self.tr("Album")),
                ('composer','varchar',self.tr("Composer")),
                ('artist','varchar',self.tr("Artist")),
                ('performer','varchar',self.tr("Performer")),
                ('conductor','varchar',self.tr("Conductor")),
                ('genre','varchar',self.tr("Genre")),
                ('date','date',self.tr("Date")),
                ('comment','text',self.tr("Comment")),
        ]
        self.tableWidget.setRowCount(len(tagList))
        for row,data in enumerate(tagList):
            self._addTag(row,*data)
        
    def _addTag(self,row,name,valueType,title):
        """Create items/widgets for a new tagtype in row *row* of the QTableWidget. *name*, *valueType* and
        *title* are attributes of the new tagtype."""
        self.tableWidget.setRowHeight(row,36) # Enough space for icons
        
        column = self._getColumnIndex('name')
        item = QtGui.QTableWidgetItem(name)
        if row <= 1:
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsEditable)
        else: item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsEditable | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        self.tableWidget.setItem(row,column,item)
        
        column = self._getColumnIndex('type')
        if row <= 1:
            item = QtGui.QTableWidgetItem('varchar')
            item.setFlags(Qt.ItemIsEnabled)
            self.tableWidget.setItem(row,column,item)
        else:
            box = QtGui.QComboBox()
            types = ['varchar','text','date']
            box.addItems(types)
            box.setCurrentIndex(types.index(valueType))
            self.tableWidget.setIndexWidget(self.tableWidget.model().index(row,column),box)
        
        column = self._getColumnIndex('title')
        item = QtGui.QTableWidgetItem(title)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsEditable)
        self.tableWidget.setItem(row,column,item)
        
        column = self._getColumnIndex('icon')
        label = IconLabel(':omg/tags/{}.png'.format(name))
        self.tableWidget.setIndexWidget(self.tableWidget.model().index(row,column),label)
        
        column = self._getColumnIndex('private')
        item = QtGui.QTableWidgetItem()
        if row <= 1:
            item.setFlags(Qt.ItemIsEnabled) # Insert an empty item that is not editable
        else:
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
        self.tableWidget.setItem(row,column,item)
    
    def finish(self):
        """Read tag information from table, check it (invalid or duplicate tag names?) and write it to the
        tagids table."""
        # Read tags
        tags = collections.OrderedDict()
        for row in range(self.tableWidget.rowCount()):
            column = self._getColumnIndex('name')
            if self.tableWidget.item(row,column).checkState() != Qt.Checked:
                continue
            name = self.tableWidget.item(row,column).text()
            
            # Check invalid tag names
            if not isValidTagName(name):
                QtGui.QMessageBox.warning(self,self.tr("Invalid tagname"),
                                          self.tr("'{}' is not a valid tagname.").format(name))
                return False
            
            # Check duplicate tag names
            if name in tags:
                QtGui.QMessageBox.warning(self,self.tr("Some tags have the same name"),
                                          self.tr("There is more than one tag with name '{}'.").format(name))
                return False
                
            column = self._getColumnIndex('type')
            if row <= 1:
                valueType = self.tableWidget.item(row,column).text()
            else: valueType = self.tableWidget.indexWidget(
                                                self.tableWidget.model().index(row,column)).currentText()
            
            column = self._getColumnIndex('title')
            title = self.tableWidget.item(row,column).text()
            if title == '':
                title = None
                
            column = self._getColumnIndex('icon')
            iconLabel = self.tableWidget.indexWidget(self.tableWidget.model().index(row,column))
            icon = iconLabel.path
            
            column = self._getColumnIndex('private')
            private = self.tableWidget.item(row,column).checkState() == Qt.Checked
            tags[name] = (name,valueType,title,icon,1 if private else 0,row+1)
        
        # Write tags to database
        assert db.query("SELECT COUNT(*) FROM {}tagids".format(db.prefix)).getSingle() == 0
        db.multiQuery("INSERT INTO {}tagids (tagname,tagtype,title,icon,private,sort) VALUES (?,?,?,?,?,?)"
                      .format(db.prefix),tags.values())
        
        # The first two tags are used as title and album. popitem returns a (key,value) tuple.
        config.options.tags.title_tag = tags.popitem(last=False)[0]
        config.options.tags.album_tag = tags.popitem(last=False)[0] 
        return True
        
    def _handleAddButton(self):
        """Add a new line/tagtype to the table."""
        rowCount = self.tableWidget.rowCount()
        self.tableWidget.setRowCount(rowCount+1)
        self._addTag(rowCount,'','varchar','')
        # Scroll to last line
        self.tableWidget.scrollTo(self.tableWidget.model().index(rowCount,0))
        
    def _getColumnIndex(self,columnKey):
        """Return the index of the column with the given key (i.e. the first part of the corresponding tuple
        in self.columns."""
        for i in range(len(self.columns)):
            if self.columns[i][0] == columnKey:
                return i
        raise ValueError("Invalid key {}".format(columnKey))


class SpecialTagsWidget(SettingsWidget):
    """This widget allows the user to specify the config-variables ''tags.tag_title'' and ''tags.tag_album''.
    It is only displayed when tagids is not empty, but one the defaults 'title' and 'album' is missing there.
    This happens if the user chose different names for these tags (which is not a good idea) and deleted his
    config file.
    """
    def __init__(self,installTool,titleNumber):
        super().__init__(installTool,titleNumber)
        self.setTitle(self.tr("Special tag settings"))
        
        label = QtGui.QLabel(self.tr(
            "One of the special tags (usually called 'title' and 'album') is missing in the tagids-table. "
            "If you chose different names for these tags, please specify those names below. "
            "If not, something is wrong with your database."))
        label.setWordWrap(True)
        self.layout().addWidget(label)
        
        formLayout = QtGui.QFormLayout()
        self.layout().addLayout(formLayout)
        self.layout().addStretch()
        
        self.titleTagLineEdit = QtGui.QLineEdit(config.options.tags.title_tag)
        self.albumTagLineEdit = QtGui.QLineEdit(config.options.tags.album_tag)
        formLayout.addRow(self.tr("Title tag"),self.titleTagLineEdit)
        formLayout.addRow(self.tr("Album tag"),self.albumTagLineEdit)
        
    def finish(self):
        """Check whether tags exist and have correct type and store them in config variables."""
        titleTag = self.titleTagLineEdit.text()
        albumTag = self.albumTagLineEdit.text()
        
        tags = list(db.query("SELECT tagname FROM {}tagids".format(db.prefix)).getSingleColumn())
        
        for tag in [titleTag,albumTag]:
            if tag not in tags:
                QtGui.QMessageBox.warning(self,self.tr("Tag does not exist"),
                                          self.tr("There is no tag of name '{}'.").format(tag))
                return False
            if db.query("SELECT COUNT(*) FROM {}tagids "
                        "WHERE tagname = ? AND tagtype = 'varchar' AND private = 0".format(db.prefix),
                        tag).getSingle() == 0:
                QtGui.QMessageBox.warning(self,self.tr("Invalid tag"),
                                          self.tr("The tag '{}' is either not of type 'varchar' or private.")
                                            .format(tag))
                return False
        
        config.options.tags.title_tag = titleTag
        config.options.tags.album_tag = albumTag
        return True
        
        
def getIcon(name):
    """Return a QIcon for the icon with the given name."""
    return QtGui.QIcon(":omg/icons/" + name)


class IconLabel(QtGui.QLabel):
    """Label for the icon column in TagWidget. It displays the icon and provides a contextmenu to change
    or remove it.
    """
    def __init__(self,path):
        super().__init__()
        self.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.setPath(path)
        
    def setPath(self,path):
        """Set the icon path."""
        pixmap = QtGui.QPixmap()
        if path is not None and pixmap.load(path):
            pixmap = pixmap.scaled(32,32,transformMode=Qt.SmoothTransformation)
        self.path = path
        self.setPixmap(pixmap)
                
    def contextMenuEvent(self,event):
        menu = QtGui.QMenu(self)
        if self.path is None:
            changeAction = QtGui.QAction(self.tr("Add icon..."),menu)
        else:changeAction = QtGui.QAction(self.tr("Change icon..."),menu)
        changeAction.triggered.connect(lambda: self.mouseDoubleClickEvent(None))
        menu.addAction(changeAction)
        
        removeAction = QtGui.QAction(self.tr("Remove icon"),menu)
        removeAction.setEnabled(self.path is not None)
        removeAction.triggered.connect(lambda: self.setPath(None))
        menu.addAction(removeAction)
        menu.exec_(event.globalPos())
        
    def mouseDoubleClickEvent(self,event):
        result = iconchooser.IconChooser.getIcon([':omg/tags'], self)
        if result:
            self.setPath(result[1])

def run():
    """Run the install tool."""
    global app
    app = QtGui.QApplication([])
    from omg import resources
    widget = InstallToolWindow()
    widget.show()
    app.exec_()
    
if __name__ == "__main__":
    run()
    
