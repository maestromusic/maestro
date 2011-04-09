# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer, Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
# This module handles configuration options from files and from the command line.

import os, sys
from omg import constants, logging
from . import configobj

CONFDIR = None

options = None
storage = None
optionObject = None
storageObject = None

logger = logging.getLogger("config")

def init(cmdOptions = []):
    """Initialize the config-module: Read the config files and create the module variables.  *cmdOptions* is a list of options given on the command line that will overwrite the corresponding option from the file or the default. Each list item has to be a string like ``main.collection=/var/music``."""
    
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
    optionObject = Config(cmdOptions,storage=False)
    options = ValueSection(optionObject)
    storageObject = Config([],storage=True)
    storage = ValueSection(storageObject)


class Option:
    """Baseclass for options. An option has the following attributes:
    
            * ``name``: Its name,
            * ``default``: the default value,
            * ``fileValue``: the value in the config file or ``None`` if the file does not contain this option,
            * ``value``:  ``None`` or a value set from the program which will overwrite fileValue during runtime, but will not be written to the config file (this is used when options are specified on the command line).
            * description (optional): A short text describing the option.
            
    \ """
    def __init__(self,name,default,description=""):
        self.name = name
        self.default = default
        self.value = None
        self.fileValue = None
        self.description = description
    
    def getValue(self):
        """Return the current value of this option. The value is the first of the attributes ``value``, ``fileValue`` which is not ``None`` or ``default`` if both are ``None``.
        """
        if self.value is not None:
            return self.value
        elif self.fileValue is not None:
            return self.fileValue
        else: return self.default

    
class ConfigOption(Option):
    """Subclass of :class:`Option` which has additionally a type. This class is used for the options in the config file."""
    def __init__(self,name,type,default,description=""):
        Option.__init__(self,name,default,description)
        self.type = type

    def _import(self,value):
        """Convert the string *value* (from the config file) into the type of this option. Raise a :class:`ConfigError` if that fails."""
        if isinstance(value,self.type):
            return value

        if self.type == bool:
            # bool("0") or bool("False") are True, but we want them to be false as this is what you type in a configuration file to make a variable false.
            if value == "0" or value.lower() == "false":
                return False
            else: return self.type(value)
        elif self.type in (int, str):
            return self.type(value)
        elif self.type == list and isinstance(value, str):
            return [x.strip(" \t") for x in value.split(",")]
        else:
            raise ConfigError("{} has type {} which does not match type {} of this option and can't be converted"
                                 .format(value,type(value),self.type))

    def _export(self,value):
        """Convert *value* (of type ``self.type``) into a string (for the config file)."""
        if self.type == bool:
            return "True" if value else "False"
        elif self.type == list:
            return ", ".join(str(v) for v in value)
        else: return str(value)

    def updateValue(self,value,fileValue):
        """Set the value of this option to *value*. If *fileValue* is true, the value will be written to the config file at application end."""
        if fileValue:
            self.fileValue = self._import(value)
            self.value = None # Otherwise getValue would return self.value
        else: self.value = self._import(value)

    def _write(self,fileSection):
        """Write the ``fileValue`` of this option in *fileSection* which must be a ``confobj.Section``-instance. If ``fileValue`` is ``None`` the option will be deleted from *fileSection*."""
        if self.name in fileSection:
            # Do not remove the value from the file even if it is the default.
            if self.fileValue is None:
                del fileSection[self.name]
            # Overwrite only if the string in the config gives a different value
            elif self.fileValue != self._importValue(fileSection[self.name]):
                fileSection[self.name] = self._exportValue(self.fileValue)
        elif self.fileValue is not None:
            fileSection[self.name] = self._exportValue(self.fileValue)


class StorageOption(Option):
    """Subclass of :class:`Option` for options in the Storage file. These options do not have a type but may store dicts, list, tuples of basic datatypes."""
    def updateValue(self,value,fileValue):
        """Set the value of this option to *value*. If *fileValue* is true, the value will be written to the config file at application end."""
        if fileValue:
            self.fileValue = value
            self.value = None # Otherwise getValue would return self.value
        else: self.value = value
        
    def _write(self,fileSection):
        """Write the ``fileValue`` of this option in *fileSection* which must be a ``confobj.Section``-instance. If ``fileValue`` is ``None`` the option will be deleted from *fileSection*."""
        if self.name in fileSection:
            if self.fileValue is None or self.fileValue == self.default:
                del fileSection[self.name]
            else: fileSection[self.name] = self.fileValue
        elif self.fileValue is not None and self.fileValue != self.default:
            fileSection[self.name] = self.fileValue


class ConfigSection:
    """A section of the configuration. It may contain options and other sections (its "members") which can be accessed via attribute- or item-access (e.g. ``main.collection`` or ``main['collection']``. The parameter *storage* holds whether this section is from the storage file."""
    def __init__(self,name,storage,members):
        self._name = name
        self._storage = storage
        self._members = {}
        for name,member in members.items():
            if isinstance(member,dict):
                self._members[name] = ConfigSection(name,storage,member)
            else:
                if storage:
                    self._members[name] = StorageOption(name,*member)
                else: self._members[name] = ConfigOption(name,*member)

    def __getitem__(self,member):
        return self._members[member]

    def __getattr__(self,member):
        if member in self._members:
            return self._members[member]
        else: raise AttributeError("Section '{}' has no member '{}'".format(self._name,member))

    def __contains__(self,member):
        return member in self._members

    def __str__(self):
        return self._name

    def updateFromFile(self,fileSection,path):
        """Read the *fileSection* (of type ``configobj.Section``) and update this section (options and subsections) with the values from the file. If *fileSection* contains an unknown option, skip it and log a warning. The parameter *path* is only used for these warnings and should contain the path to the config file."""
        for name,member in fileSection.items():
            if isinstance(member,configobj.Section):
                if name not in self._members:
                    logger.error("Error in config file '{}': Unknown section '{}' in section '{}'."
                                    .format(path,name,self._name))
                elif isinstance(self._members[name],Option):
                    logger.error("Error in config file '{}': '{}' is not a section in section '{}'."
                                    .format(path,name,self._name))
                else:
                    self._members[name].updateFromFile(member,path)
            else:
                if name not in self._members:
                    logger.error("Error in config file '{}': Unknown option '{}' in section '{}'."
                                    .format(path,name,self._name))
                elif isinstance(self._members[name],ConfigSection):
                    logger.error("Error in config file '{}': '{}' is not an option in section '{}'."
                                    .format(path,name,self._name))
                else:
                    self._members[name].updateValue(member,fileValue=True)

    def _write(self,fileSection):
        """Write this section and its options and subsections into *fileSection* (of type ``configobj.Section``). This will not really write the file."""
        if self._name not in fileSection or not isinstance(fileSection[self._name],configobj.Section):
            fileSection[self._name] = {}
        for name,member in self._members.items():
            member._write(fileSection[self._name])


class Config(ConfigSection):
    """This is the main object of the config-module and stores the configuration of one config file. It is itself a section with the name ``<Default>``. Upon creation this class will read the defaults and then the config/storage-file.The parameters are:

        * *cmdOptions*: a list of strings of the form ``main.collection=/var/music``. The options given in these strings will overwrite the options from the file or the defaults.
        * *storage*: whether this object corresponds to a storage file (confer module documentation).

    \ """
    def __init__(self,cmdConfig,storage):
        ConfigSection.__init__(self,"<Default>",storage,{})

        self._path = os.path.join(CONFDIR,"storage" if self._storage else "config")
        if os.path.exists("{}.{}".format(self._path,constants.VERSION)):
            self._path = "{}.{}".format(self._path,constants.VERSION) # Load version specific config

        # First read the default config
        from . import defaultconfig
        defaults = defaultconfig.storage if storage else defaultconfig.defaults
        for sectionName,sectionDict in defaults.items():
            self._addSection(sectionName,sectionDict)

        # Then read the config file
        self._openFile()
        for sectionName,section in self._configObj.items():
            if not isinstance(section,configobj.Section):
                logger.error("Error in config file '{}': Option '{}' does not belong to any section."
                                .format(self._path,sectionName))
            if sectionName in self._members:
                self._members[sectionName].updateFromFile(section,self._path)
        # Let the file open until plugin config is loaded
        
        # Then consider cmdConfig
        for line in cmdConfig:
            try:
                option, value = (s.strip() for s in line.split('=',2))
                keys = option.split('.')
                section = self
                for key in keys[:-1]:
                    section = section[key]
                section[keys[-1]].updateValue(value,fileValue=False)
            except KeyError:
                logger.error("Unknown config option on command line '{}'.".format(option))
            except Exception:
                logger.error("Invalid config option on command line '{}'.".format(line))

    def _openFile(self):
        """Open the file this object corresponds to and store a ``configobj.ConfigObj``-object in ``self._configObj``."""
        self._configObj = configobj.ConfigObj(self._path,encoding='UTF-8',
                                              create_empty=True,unrepr=self._storage)
        
    def _addSection(self,name,options):
        if name in self._members:
            raise ConfigError("Error in config file '{}': Cannot add section '{}' twice.".format(self._path,name))
        else: self._members[name] = ConfigSection(name,self._storage,options)

    def loadPlugins(self,sections):
        for name,section in sections.items():
            self._addSection(name,section)
            if self._configObj is None: # This is the case if plugins are loaded during runtime
                self._openFile()
            if name in self._configObj:
                self._members[name].updateFromFile(self._configObj[name],self._path)
        self._configObj = None

    def removePlugins(self,sectionNames):
        for name in sectionNames:
            if name not in self._members:
                raise ConfigError("Cannot remove plugin section '{}' from config because it doesn't exist.".format(name))
            del self._members[name]

    def write(self):
        self._openFile()
        for section in self._members.values():
            section._write(self._configObj)
        self._configObj.write()
        self._configObj = None
            
    def pprint(self):
        for section in self._members.values():
            self.pprintSection(section,1)

    def pprintSection(self,section,nesting):
        print(("    "*(nesting-1))+('['*nesting)+section._name+(']'*nesting))
        for member in section._members.values():
            if isinstance(member,ConfigSection):
                print()
                self.pprintSection(member,nesting+1)
            else: print("{}{}: {}".format("    "*(nesting-1),member.name,member.getValue()))
        print()


class ValueSection:
    def __init__(self,section):
        self._section = section

    def __getattr__(self,name):
        result = self._section.__getattr__(name)
        if isinstance(result,Option):
            return result.getValue()
        else: return ValueSection(result)

    def __setattr__(self,name,value):
        if name == '_section':
            super().__setattr__(name,value)
        else:
            option = self._section.__getattr__(name)
            if not isinstance(option,Option):
                raise ConfigError("Cannot write sections via ValueSection (section name '{}').".format(name))
            else: option.updateValue(value,fileValue=True)

    def __getitem__(self,key):
        result = self._section.__getitem__(key)
        if isinstance(result,Option):
            return result.getValue()
        else: return ValueSection(result)

    def __setitem__(self,key,value):
        option = self._section.__getitem__(key)
        if not isinstance(option,Option):
            raise ConfigError("Cannot write sections via ValueSection (section name '{}').".format(name))
        else: option.updateValue(value,fileValue=True)


class ConfigError(Exception):
    """A ConfigError is for example raised if the config file contains invalid syntax."""
    def __init__(self, message):
        self.message = message
    
    def __str__(self):
        return "ConfigError: {}".format(self.message)
