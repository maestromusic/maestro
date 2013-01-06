# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2013 Martin Altmayer, Michael Helmling
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
This package handles OMG's configuration. There are five sources where configuration may come from:
Three files in the configuration directory, the default options which are hard coded into the
:mod:`defaultconfig <omg.config.defaultconfig>` module (and into plugins) and finally the command line where
arbitrary config options may be overwritten using the -c option.
The three files are:

    * ``config``. This is the main configuration file and the one that is mainly edited by the user.
      But it may be written from the program, too. It contains several sections which may contain options
      and nested sections. Options must have a type (str,int,bool or list) and a default value stored in
      defaultconfig. To get the option ``size`` from the section ``gui`` simply use ::
    
        config.options.gui.size
      
      This will directly return the option's value. In the rare cases you need
      the option itself as :class:`ConfigOption`-instance use ``config.optionObject.gui.size``.
      
      Instead of attribute access you may also use item access::
      
          config.options['gui']['size']
        
      Both types of access allow to write values via assignment.
      Note that values will not be written to the file before the application terminates, though.

    * ``storage``. This file also holds persistent information but is mainly written by the program. It uses
      JSON notation, so it can store any combination of Python's standard types including lists and dicts.
      The file is human readable and can be edited by the user (less comfortable than config).
      Access works like for config, but with the variables ``config.storage`` and ``config.storageObject``.

    * ``binary``. The last file contains simply a pickled dict to store arbitrary binary data. During the
      application this dict can be accessed via ``config.binary`` which really is simply a dict, so there are
      no sections or attribute access like for ``config`` and ``storage``. Take care that your keys don't
      conflict with other modules!

Both ``config`` and ``storage`` may only contain options which are defined in the
:mod:`defaultconfig <omg.config.defaultconfig>` module or in the default configuration of a plugin that
is returned by its ``defaultConfig`` or ``defaultStorage`` method (to be precise the first level may contain
sections which are not defined. OMG will assume that they belong to a plugin that is not loaded).

Call :func:`init` at application start to read options and call :func:`shutdown` at the end to write the
options. Use :func:`loadPlugins` and :func:`removePlugins` to add or remove plugin configuration.
"""

import os, sys, pickle, collections, copy

from . import configio
from .. import constants, logging

CONFDIR = None

# These are the main access objects. The first two give direct access to the values,
# while the last two yield ConfigOption instances
options = None
storage = None
optionObject = None
storageObject = None

# A dict which will be pickled and stored in a file
binary = None

logger = logging.getLogger("config")


def init(cmdConfig = [],testMode=False):
    """Initialize the config-module: Read the config files and create the module variables. *cmdConfig* is a
    list of options given on the command line that will overwrite the corresponding option from the file or
    the default. Each list item has to be a string like ``main.collection=/var/music``.
    If *testMode* is True, a different file will be used for config options (testconfig instead of config),
    storage will be set to the default values and binary will be empty.
    """
    
    # Find the config directory and ensure that it exists
    global CONFDIR
    if 'XDG_CONFIG_HOME' in os.environ: 
        CONFDIR = os.path.join(os.environ['XDG_CONFIG_HOME'], 'omg') 
    else: CONFDIR = os.path.join(constants.HOME, ".config", "omg")

    if not os.path.exists(CONFDIR):
        try:
            os.makedirs(CONFDIR) # also create intermediate directories
        except OSError:
            logger.exception("Could not create config directory '{}'.".format(CONFDIR))
            sys.exit(1)
    elif not os.path.isdir(CONFDIR):
        logger.warning("Config directory '{}' is not a directory.".format(CONFDIR))
        sys.exit(1)

    # Initialize config and storage
    global options, storage, optionObject, storageObject
    optionObject = MainSection(_getPath("config" if not testMode else "testconfig"),cmdConfig,storage=False)
    storageObject = MainSection(_getPath("storage") if not testMode else None,[],storage=True)
    options = ValueSection(optionObject)
    storage = ValueSection(storageObject)

    # Initialize pickled part of the configuration
    global binary
    binary = {}
    if not testMode:
        path = _getPath("binary")
        if os.path.exists(path):
            try:
                with open(path,'rb') as file:
                    binary = pickle.load(file)
            except:
                logger.exception("Could not load binary configuration from '{}'.".format(path))


def shutdown():
    """Store the configuration persistently on application shutdown."""
    optionObject.write()
    storageObject.write()
    pickle.dump(binary,open(_getPath("binary"),"wb"))


class Option:
    """Baseclass for options used by the config and storage files. An option has the following attributes:
    
            * “name”: Its name,
            * “default”: the default value,
            * “value”: the current value from the file or defaults. When this value differs from default, it
              will be written to the file at shutdown.
            
    \ """
    def __init__(self,name,default,description=""):
        self.name = name
        self.default = default
        self.resetToDefault()
        
    def getValue(self):
        """Return current value."""
        return self.value
        
    def setValue(self,value):
        """Set current value."""
        self.value = value
        
    def export(self):
        """Return current value in a format suitable for writing it to the config file (this need not be a
        string)."""
        return self.value
    
    def resetToDefault(self):
        """Set the value to a deep copy of the default value."""
        self.value = copy.deepcopy(self.default) # value may be edited, default must not change

    
class ConfigOption(Option):
    """Subclass of :class:`Option` which has additional attributes:
    
        * type: one of bool,int,str or list
        * description: an optional description
        * tempValue: None or a value set from the program which will overwrite value during runtime,
          but will not be written to the config file (this is used when options are specified on the
          command line).
    
    This class is used for the options in the config file.
    """
    def __init__(self,name,type,default,description=""):
        Option.__init__(self,name,default,description)
        self.type = type
        self.tempValue = None
        self.description = description
    
    def getValue(self,temp=True):
        """Return current value. If *temp* is True (default) and there is a temporary value, it will be
        returned."""
        if temp and self.tempValue is not None:
            return self.tempValue
        else: return self.value

    def setValue(self,value):
        """Set the option's value (or its temporary value, if *temp* is True)."""
        # At first this method deleted temporary values when a new value was written. But as we cannot
        # properly detect when values are changed (for type list), this leads to inconsistent behaviour.
        # Thus the behaviour is this: As soon as a temporary value is set you can only change the temporary
        # value. No change will be written to the file at the end.
        assert value is not None
        if self.tempValue is not None:
            self.tempValue = value
        else: self.value = value
            
    def fromString(self,value):
        """Convert the string *value* to the type of this option. Raise a ConfigError if that fails."""
        self.setValue(self.parseString(value))
        
    def parseString(self,value):
        """Convert the string *value* to the type of this option and return it. Raise a ConfigError
        if that fails."""
        assert isinstance(value,str)
        try:
            if self.type == bool:
                # bool("0") or bool("False") are True, but we want them to be false as this is what you
                # type in a configuration file to make a variable false.
                if value == "0" or value.lower() == "false":
                    return False
                else: return bool(value)
            elif self.type in (int, str):
                return self.type(value)
            elif self.type == list and isinstance(value, str):
                values = [x.strip(" \t") for x in value.split(",")]
                return  [x for x in values if len(x) > 0]
            else: raise ValueError()
        except ValueError as e:
            raise ConfigError("{} has type {} which does not match type {} of this option and "
                              "can't be converted".format(value,type(value),self.type))

    def export(self):
        value = self.getValue(temp=False)
        if self.type == bool:
            return "True" if value else "False"
        elif self.type == list:
            if len(value) == 0:
                return ""
            return ", ".join(str(v) for v in value)
        else: return str(value)


class Section:
    """A section of the configuration. It may contain options and other sections which can be accessed via
    the attribute ''members''. The parameter *storage* holds whether this section is from the storage file.
    The parameter *defaults* is used to initialize the section and determine the available options. There is
    no way to add options later on (but see MainSection.loadPlugins).
    """
    def __init__(self,name,storage,defaults):
        self.name = name
        self.storage = storage
        self.members = collections.OrderedDict()
        for name,member in defaults.items():
            if isinstance(member,dict) and (not storage or name.startswith('SECTION:')):
                self._addSection(name,member)
            else:
                if storage:
                    self.members[name] = Option(name,member)
                else: self.members[name] = ConfigOption(name,*member)

    def __str__(self):
        return self.name
    
    def __getattr__(self,name):
        return self.members[name]

    def getOptions(self):
        """Return all members which are options."""
        return (member for member in self.members.values() if isinstance(member,Option))
    
    def getSubsections(self):
        """Return all members which are nested sections."""
        return (member for member in self.members.values() if isinstance(member,Section))
        
    def updateFromDict(self,rawDict,allowUnknownSections=False):
        """Read the *rawDict* and update this section (options and subsections) with the values from
        *rawDict*. If *rawDict* contains an unknown option, skip it and log a warning. If it
        contains an unknown section, log a warning -- except when *allowUnknownSections* is True (the config
        module allows unknown sections on the first level because they might belong to plugins that are
        currently not enabled).
        
        The format of *rawDict* depends on ''self.storage'' and is the same that is returned by the
        corresponding read-methods in configio.
        """
        path = _getPath('storage' if self.storage else 'config')
        for name,member in rawDict.items():
            if isinstance(member,dict) and (not self.storage or name.startswith('SECTION:')):
                if self.storage:
                    name = name[len('SECTION:'):]
                if name not in self.members:
                    if not allowUnknownSections:
                        logger.warning("Error in config file '{}': Unknown section '{}' in section '{}'."
                                        .format(path,name,self.name))
                elif isinstance(self.members[name],Option):
                    logger.warning("Error in config file '{}': '{}' is not a section in section '{}'."
                                    .format(path,name,self.name))
                else: self.members[name].updateFromDict(member)
            else:
                if name not in self.members:
                    logger.warning("Error in config file '{}': Unknown option '{}' in section '{}'."
                                    .format(path,name,self.name))
                elif isinstance(self.members[name],Section):
                    logger.warning("Error in config file '{}': '{}' is not an option in section '{}'."
                                    .format(path,name,self.name))
                else:
                    option = self.members[name]
                    if self.storage:
                        option.setValue(member)
                    else: option.fromString(member)
                
    def _addSection(self,name,defaults):
        """Add a section as nested section. *name* is the name of the section and must start with 'SECTION:'
        in the storage case. *defaults* are the default values (usually a part of the dicts in
        defaultconfig).
        """
        if self.storage:
            assert name.startswith('SECTION:')
            name = name[len('SECTION:'):]
        self.members[name] = Section(name,self.storage,defaults)
        return self.members[name]
    
    def _toRawDict(self):
        """Return the values of this section as a raw dict. The format of this dict depends on
        ''self.storage'' and is the same that is expected by the corresponding write functions in configio.
        """
        items = []
        for name,member in self.members.items():
            if isinstance(member,Section):
                if self.storage:
                    name = 'SECTION:'+name
                items.append((name,member._toRawDict()))
            else: items.append((name,member.export()))
        return collections.OrderedDict(items)


class MainSection(Section):
    """This is the main object of the config-module and stores the configuration of one config file.
    It is itself a section with the name ''<Main>''. The parameters are:

        * *path*: path to the config file. May be None in which case no file is used.
        * *cmdConfig*: a list of strings of the form “main.collection=/var/music”. The options given in
          these strings will overwrite the options from the file or the defaults.
        * *storage*: whether this object corresponds to a storage file (confer module documentation).

    On initialization this object will read the correct default values, overwrite them with values from
    the corresponding file and (if storage is False) finally set temporary values according to *cmdConfig*.
    \ """
    def __init__(self,path,cmdConfig,storage):
        # First initialize with default values
        from . import defaultconfig
        defaults = defaultconfig.storage if storage else defaultconfig.defaults
        Section.__init__(self,"<Main>",storage,defaults)

        # Then update with values from config/storage file
        self._path = path
        if path is not None:
            from . import configio
            try:
                if storage:
                    self._rawDict = configio.readStorage(self._path)
                else: self._rawDict = configio.readConfig(self._path)
                # Allow unknown sections on first level as they might be plugin configurations
                self.updateFromDict(self._rawDict,allowUnknownSections=True)
            except configio.ConfigError as e:
                logger.critical(str(e))
                logger.critical("There is an error in config file '{}'. Deleting the file should help "
                                "(but also erase your configuration...).".format(self._path))
                sys.exit(1)
                
        # Finally set temporary values from cmdConfig
        if not storage:
            for line in cmdConfig:
                try:
                    option, value = (s.strip() for s in line.split('=',2))
                    keys = option.split('.')
                    section = self
                    for key in keys[:-1]:
                        section = section.members[key]
                    option = section.members[keys[-1]]
                    option.tempValue = option.parseString(value)
                except KeyError:
                    logger.error("Unknown config option on command line '{}'.".format(line))
                except Exception as e:
                    logger.error("Invalid config option on command line '{}'.".format(line))
    
    def loadPlugins(self,sections):
        """Load plugin configuration. *sections* stores the default configuration of the plugins. It is a
        dict mapping section names (usually the plugin name) to a section dict like in the defaultconfig
        module. After storing this default configuration, check if these sections exist in the config and
        storage file and read values from there.
        """
        for name,section in sections.items():
            section = self._addSection(name,section)
            if name in self._rawDict:
                section.updateFromDict(self._rawDict[name])

    def removePlugins(self,sectionNames):
        """Remove the plugin configuration of one or more plugins. *sectionNames* contains the names of the
        sections used by the plugins that should be removed."""
        for name in sectionNames:
            if self.storage:
                assert name.startswith('SECTION:')
                name = name[len('SECTION:'):]
            if name not in self.members:
                raise ConfigError("Cannot remove plugin section '{}' from config because it doesn't exist."
                                  .format(name))
            del self.members[name]
    
    def write(self):
        """Write this configuration to the correct file."""
        if self._path is not None:
            try:
                if self.storage:
                    configio.writeStorage(self._path,self)
                else: configio.writeConfig(self._path,self)
            except configio.ConfigError as e:
                logger.error(e)
        
    def pprint(self):
        """Debug method: Print this configuration."""
        for section in self.members.values():
            self._pprintSection(section,1)

    def _pprintSection(self,section,nesting):
        """Helper for pprint: PPrint a section."""
        print(("    "*(nesting-1))+('['*nesting)+section.name+(']'*nesting))
        for member in section.members.values():
            if isinstance(member,Section):
                print()
                self._pprintSection(member,nesting+1)
            else: print("{}{}: {}".format("    "*(nesting-1),member.name,member.getValue()))
        print() # empty line


class ValueSection:
    """A ValueSection wraps a Section to provide easy access to the actual configuration values (by-passing
    instances of Option and Section). On attribute access or item access it will directly return the option's
    value or -- when accessing a subsection -- a ValueSection wrapping the subsection.
    This class is used by ``config.options`` and ``config.storage``.
    """
    def __init__(self,section):
        self._section = section

    def __getattr__(self,name):
        result = self._section.members[name]
        if isinstance(result,Option):
            return result.getValue()
        else: return ValueSection(result)

    def __setattr__(self,name,value):
        if name == '_section':
            super().__setattr__(name,value)
        else:
            option = self._section.members[name]
            if not isinstance(option,Option):
                raise ConfigError("Cannot write sections via ValueSection (section name '{}').".format(name))
            else: option.setValue(value)

    def __getitem__(self,key):
        result = self._section.members[key]
        if isinstance(result,Option):
            return result.getValue()
        else: return ValueSection(result)

    def __setitem__(self,key,value):
        option = self._section.members[key]
        if not isinstance(option,Option):
            raise ConfigError("Cannot write sections via ValueSection (section name '{}').".format(key))
        else: option.setValue(value)


def _getPath(fileName):
    """Get the path to a configugation file. *fileName* may be ``'config'`` or ``'storage'`` or``'binary'``.
    This method checks for version-dependent config-files.
    """
    path = os.path.join(CONFDIR,fileName)
    if os.path.exists("{}.{}".format(path,constants.VERSION)):
        return "{}.{}".format(path,constants.VERSION) # Load version specific config
    else: return path
    