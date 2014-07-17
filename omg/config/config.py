# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
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

import re, os, collections, copy

_types = {} # types of config files. Maps name to the corresponding class (see registerConfigType)
_files = [] # registered config files (see addFile)


class ConfigError(Exception):
    """A ConfigError is for example raised if the configuration file contains invalid syntax."""


def registerConfigType(name, theClass):
    """Register a new type of configuration file. *name* is the identifier that must be passed to 'addFile'
    to create such a file. *theClass* is the class responsible for handling such files.
    """
    _types[name] = theClass
    
def unregisterConfigType(name):
    """Unregister a configuration file type."""
    del _types[name]
    
    
def defaultConfigDirectory(name):
    """Return a reasonable directory for configuration files. *name* should be the name of your application.
    """ 
    if 'XDG_CONFIG_HOME' in os.environ: 
        return os.path.join(os.environ['XDG_CONFIG_HOME'], name) 
    else: return os.path.join(os.path.expanduser("~"), ".config", name)


def addFile(type, *args, **kwargs):
    """Add a configuration file to the application and return a File-object. *type* is the file type
    (one of 'config', 'json', 'pickle' or a name registered with 'registerConfigType'). All other arguments
    are passed to the corresponding class.
    
    Note that the file on disk is not read until either 'read' or 'getAccess' is called.
    """
    if type in _types:
        file = _types[type](*args, **kwargs)
        _files.append(file)
        return file
    else: raise ValueError("'{}' is not a valid argument for config.addFile.".format(type))
    
def removeFile(file):
    """Remove a configuration file from the application without deleting the file from disk."""
    _files.remove(file)
    
def deleteFile(file):
    """Remove a configuration file from the application and delete it from disk."""
    if os.path.exists(file.path):
        os.remove(file.path)
    removeFile(file)
    
    
def writeAll():
    """Write all configuration files to disk."""
    for file in _files:
        file.write()
        
    
def getFile(access):
    """Return a File-object from an Access-object."""
    if not isinstance(access, Access):
        raise TypeError("access must be a config.Access-instance.") 
    return access._file

def getOption(access, option):
    """Shortcut: Given an Access-instance and a key string (e.g. 'gui.browser.width') return the
    Option-instance (which is not the option value!) for this option.
    """ 
    if not isinstance(access, Access):
        raise TypeError("access must be a config.Access-instance.") 
    return getFile(access).getOption(option)


class Option:
    """Baseclass for options used by all files. An option has the following attributes:
        * 'name': Its name,
        * 'default': the default value,
        * 'value': the current value from the file or defaults. When this value differs from default, it
          will be written to the file when 'write' is called.   
        * description: an optional description string.   
    """
    def __init__(self, name, default, description=None):
        self.name = name
        self.default = default
        self.description = description
        self.resetToDefault()
        
    def getValue(self):
        """Return current value."""
        if hasattr(self, 'tempValue'):
            return self.tempValue
        else: return self.value
        
    def setValue(self, value):
        """Set current value."""
        # When a temporary value is set, it is not possible to change the actual value.
        # Otherwise behavior would be inconsistent, since mutable temporary values (e.g. a list) are
        # usually changed without this method.
        if hasattr(self, 'tempValue'):
            self.tempValue = value
        else: self.value = value
    
    def resetToDefault(self):
        """Set the value to a deep copy of the default value."""
        self.setValue(copy.deepcopy(self.default)) # value may be edited, default must not change
        
    def _fromFileValue(self, value):
        """Like setValue but *value* is in the format used in the option file.""" 
        self.setValue(value)
        
        
class TypedOption(Option):
    """Subclass of Option which has an additional attribute 'type': One of bool, int, str or list.
    This class is used for the options in the 'config' file type.
    """
    def __init__(self, name, type, default, description=None):
        super().__init__(name, default, description)
        self.type = type
        
    def parseString(self, value):
        """Convert the string *value* to the type of this option and return it. Raise a ConfigError
        if that fails."""
        if not isinstance(value, str):
            raise TypeError()
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
                              "can't be converted".format(value, type(value), self.type))
            
    def _fromFileValue(self, value):
        self.setValue(self.parseString(value))

        
class Section:
    """A section of the configuration. It may contain options and subsections both of which can be accessed
    via the attribute 'members' or via attribute access.
    *name* is the name of this section.
    The parameter *data* defines which options (and subsections) are available and what the default
    values are.
    """
    # Subclasses of Section can change the class used for options with this attribute.
    optionClass = Option
    
    def __init__(self, name, data):
        self.name = name
        self.members = collections.OrderedDict()
        for name, data in data.items():
            self._add(name, data)

    def __str__(self):
        return self.name
    
    def __getattr__(self,name):
        return self.members[name]

    def getOptions(self):
        """Return all members which are options."""
        return (member for member in self.members.values() if isinstance(member, Option))
    
    def getSubsections(self):
        """Return all members which are nested sections."""
        return (member for member in self.members.values() if isinstance(member, Section))
    
    def addSection(self, name, data):
        """Add a new subsection to this section and return it."""
        if not isinstance(data, dict):
            raise TypeError("'data' argument must be a dict.")
        self._add(name, data)
        return self.members[name]
    
    def _add(self, name, data): # add option or section
        if isinstance(data, dict):
            self.members[name] = Section(name, data)
        else:
            if not isinstance(data, tuple):
                data = (data,)
            self.members[name] = self.optionClass(name, *data)
        
    def removeSection(self, name):
        """Remove an existing section from this one."""
        if name not in self.members:
            raise KeyError("Cannot remove non-existent section '{}'".format(name))
        del self.members[name]
        
    def _updateFromDict(self, rawDict, allowUndefinedSections=False, errorMethod=None):
        """Read the *rawDict* and update this section (options and subsections) with the values from
        *rawDict*. If a minor error occurs (e.g. undefined option) call *errorMethod* with an error string
        as argument. If *allowUndefinedSections* is True, don't call *errorMethod* for direct subsections
        (instead assume that they are configuration for some plugin which is currently disabled).
        """
        for name, data in rawDict.items():
            if name not in self.members:
                if not (isinstance(data, dict) and allowUndefinedSections) and errorMethod is not None:
                    errorMethod("Undefined option/section '{}' in section '{}'.".format(name, self.name))
                #else: do not add the section
            else:
                member = self.members[name]
                if isinstance(member, Section):
                    if not isinstance(data, dict) and errorMethod is not None:
                        errorMethod("'{}' is not an option but a section (in '{}').".format(name, self.name))
                    else: self.members[name]._updateFromDict(data, errorMethod=errorMethod)
                else:
                    self.members[name]._fromFileValue(data)
                    
    def _toRawDict(self):
        """Return a raw dict for this section, i.e. replace Sections by dicts and options by their value."""
        rawDict = collections.OrderedDict()
        for name, member in self.members.items():
            if isinstance(member, Section):
                rawDict[name] = member._toRawDict()
            else: rawDict[name] = member.value
        return rawDict


class ConfigSection(Section):
    """Section-class used in files of type 'config'."""
    optionClass = TypedOption
        
    def _add(self, name, data):
        if isinstance(data, dict):
            self.members[name] = ConfigSection(name, data)
        elif not isinstance(data, tuple): # disable automatic conversion to tuple in super class
            raise ValueError("No type is specified for option '{}'".format(name))
        else:
            super()._add(name, data)
    
    
class File:
    """Abstract super class for configuration files. Use 'addFile' to create instances. This class offers
    methods to manage the file (i.e. 'write'). In order to access the configuration values you should obtain
    an Access-instance via 'getAccess'.
    
    Note that options are not read from file until either 'read' or 'getAccess' is called.
    
    Arguments:
        - *path*: The absolute path to the configuration file. May be None in which case all options
          will be set to their default values and nothing is written to disk.
        - *options*: Defines which options and sections are available and what the default values are.
        - *allowUndefinedSections*: Don't treat undefined sections on the first level as errors. Use this
          if you want to add sections later on (e.g. when a plugin is enabled).
        - *version*: A version string. If it exists, the file *path*+*version* will be loaded instead of
          *path*. When this feature is used, it is possible to have different configuration files for
          different program versions.
        - *errorMethod*: If not None this method is called on minor errors with an errors string as argument.
          Use this to e.g. log minor errors to console.
          
    To create custom configuration file formats, create a subclass that implements '_read' and '_write'.
    """
    # Subclasses of File can change the class used for sections with this attribute.
    sectionClass = Section
    
    def __init__(self, path, options, allowUndefinedSections=False, version=None, errorMethod=None):
        if version is not None:
            versionPath = path+'.'+version
            if os.path.exists(versionPath):
                path = versionPath
        self.path = path
        self.allowUndefinedSections = allowUndefinedSections
        self.errorMethod = errorMethod
        # name of the main section is only relevant for debugging
        self.section = self.sectionClass("<Main({})>".format(os.path.basename(self.path)), options)
        # store the raw dict found in the file. When sections are added later on, we can lookup the values
        # without reading the file again.
        self._rawDict = None
        
    def read(self):
        """Read options from disk. Throw a ConfigError if that fails."""
        if self.path is None:
            return
        try:
            self._rawDict = self._read()
            self.section._updateFromDict(self._rawDict, allowUndefinedSections=self.allowUndefinedSections,
                                         errorMethod=self.errorMethod)
        except ConfigError as e:
            raise ConfigError("There is an error in config file '{}'. Deleting the file should help "
                              "(but also erase your configuration...). ({})".format(self.path, str(e)))
    
    def _read(self):
        """Read and return a raw dict from file or raise a ConfigError if that fails. A raw dict contains
        all options and sections found in the file (even those that were not defined when creating this
        File). Option names are mapped to the corresponding values (before they are stored in the option,
        values are passed through Option._fromFileValue). Section names are mapped to raw dicts which
        contain the sections' contents.
        """
        raise NotImplementedError()
    
    def write(self):
        """Write options to disk. Throw a ConfigError if that fails."""
        if self.path is None:
            return
        try:
            self._write()
        except ConfigError as e:
            raise ConfigError("Configuration file '{}' was not written. ({})".format(self.path, str(e)))
        
    def _write(self):
        """Write values that differ from their default values to disk. Raise a ConfigError on fail."""
        raise NotImplementedError()
    
    def addSections(self, sections):
        """Add sections. *sections* is a dict mapping section names to a section dict (equivalent to the
        'options' argument to the constructor. If *allowUndefinedSections* was set to True in the
        constructor, sections may be added after 'read' has been called: Values from undefined sections will
        be remembered internally and used when the section is added later.
        """
        for sectionName, options in sections.items():
            section = self.section.addSection(sectionName, options)
            if sectionName in self._rawDict:
                section._updateFromDict(self._rawDict[sectionName], errorMethod=self.errorMethod)

    def removeSections(self, sectionNames):
        """Remove all sections whose name is in the given list."""
        for name in sectionNames:
            self.section.removeSection(name)
            
    def getAccess(self):
        """Return an Access-object for this file."""
        if self._rawDict is None:
            self.read()
        return Access(self, self.section)
    
    def getOption(self, key):
        """Get an Option-instance by a key string like 'gui.browser.width'."""
        keys = key.split('.')
        section = self.section
        for key in keys[:-1]:
            section = section.members[key]
        option = section.members[keys[-1]]
        if isinstance(option, Option):
            return option
        else: raise ValueError("'{}' is not a valid option key.".format(key))
        
    def setTemporaryValue(self, key, value):
        """Set an option (see 'getOption') to a temporary value. Temporary values are not written to disk.
        """
        self.getOption(key).tempValue = value
        
    def unsetTemporaryValue(self, key):
        """Remove the temporary value of an option (see getOption)."""
        option = self.getOption(key)
        if hasattr(option, 'tempValue'):
            del option.tempValue 
    
        
class ConfigFile(File):
    """This class represents configuration files of type 'config'. The following example describes the
    format of such files. 
        
        [gui]
        maximized = True
        
        # Note that subsections are defined by using multiple brackets.
        [[browser]]
        width = 300
        
        [database]
        host = localhost
    
    """
    sectionClass = ConfigSection
    
    # Pattern to match section headers, normal lines and empty lines/comments in config files
    sectionPattern = re.compile('\s*(\[+)([^\]]+)(\]+)\s*$')
    linePattern = re.compile('([^=]+)=(.*)$')
    ignorePattern = re.compile('\s*(#.*)?$')
        
    def setTemporaryValue(self, key, value):
        # Allow submitting strings for options of other types by using 'parseString'.
        # This makes it easier to set temporary values via command line options.
        if isinstance(value, str):
            option = self.getOption(key)
            if option.type is not str:
                value = option.parseString(value)
        super().setTemporaryValue(key, value)
        
    def _read(self):
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, 'r') as file:
                lines = [line.rstrip() for line in file.readlines()]
        except:
            raise ConfigError("Cannot read file")
        
        config = collections.OrderedDict()
        sections = [config]
        for lineNumber, line in enumerate(lines):
            currentSection = sections[-1]
            if self.ignorePattern.match(line):
                continue
            
            matchObj = self.sectionPattern.match(line)
            if matchObj is not None:
                depth = len(matchObj.group(1))
                name = matchObj.group(2).strip()
                if len(matchObj.group(3)) != depth: # closing brackets must match opening brackets
                    raise ConfigError("Syntax error in line {}".format(lineNumber))
                if depth > len(sections) + 1: # Too many brackets
                    raise ConfigError("Syntax error in line {}".format(lineNumber))
                if depth < len(sections) + 1:
                    # close current section and go upwards
                    sections = sections[:depth]
                    currentSection = sections[-1]
                # Finally create a new section
                if name in currentSection:
                    raise ConfigError("Cannot create section '{}' because there is already an option with "
                                      "the same name (line {}).".format(name, lineNumber))
                currentSection[name] = collections.OrderedDict()
                sections.append(currentSection[name])
                continue
            
            matchObj = self.linePattern.match(line)
            if matchObj is not None:
                name = matchObj.group(1).strip()
                value = matchObj.group(2).strip()
                if name in currentSection and errorMethod is not None:
                    raise ConfigError("Option '{}' appears twice (linenumber {})".format(name, lineNumber))
                currentSection[name] = value
                continue
                
            # Neither pattern matched
            raise ConfigError("Syntax error in line {}".format(lineNumber))
                
        return config
        
    def _write(self):
        outputLines = [] # these lines, joined by \n, will form the final file
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            if not os.path.exists(self.path):
                inputLines = []
            else:
                with open(self.path, 'r') as file:
                    inputLines = [line.rstrip() for line in file.readlines()]
        except:
            raise ConfigError("Cannot read file.")
        
        self._compareAndWriteSection(self.section, 0, inputLines, 0, outputLines)
        
        try:
            with open(self.path, 'w') as file:
                file.write('\n'.join(outputLines))
        except:
            raise ConfigError("Cannot write file")
    
    def _compareAndWriteSection(self, section, depth, inputLines, pos, outputLines):
        """Starting at position *pos*, read the input lines, compare the values within to the values from
        *section* and append output lines (keeping comments or lines with unchanged values, adding changed
        values etc.). Handle subsections recursively. *depth* is the depth of section (the number of opening
        brackets in its title line.
        """
        writtenOptions = []
        writtenSubsections = []
        # Before the first subsection we must write all options
        remainingOptionsWritten = False
        
        if depth > 0:
            outputLines.append('['*depth+section.name+']'*depth)
        startLen = len(outputLines)
        
        while pos < len(inputLines):
            line = inputLines[pos]
            
            # Handle option lines
            matchObj = self.linePattern.match(line)
            if matchObj is not None:
                name = matchObj.group(1).strip()
                value = matchObj.group(2).strip()
                if name not in section.members.keys() or not isinstance(section.members[name], TypedOption):
                    # undefined option, keep it
                    outputLines.append(line)
                else:
                    option = section.members[name]
                    if self._isValueCorrect(option, value):
                        outputLines.append(line)
                    else: self._writeOption(option, outputLines)
                    writtenOptions.append(option.name)
                pos += 1
                continue
            
            # Handle section lines
            matchObj = self.sectionPattern.match(line)
            if matchObj is not None:
                if not remainingOptionsWritten:
                    remainingOptionsWritten = True
                    for option in section.getOptions():
                        if option.name not in writtenOptions:
                            self._writeOption(option, outputLines)
                sectionDepth = len(matchObj.group(1))
                name = matchObj.group(2).strip()
                if sectionDepth == depth + 1 and name in section.members \
                        and isinstance(section.members[name], Section):
                    # this is a subsection
                    pos = self._compareAndWriteSection(section.members[name], sectionDepth, inputLines,
                                                  pos+1, outputLines)
                    writtenSubsections.append(section.members[name].name)
                    continue
                else: break    
                
            # Keep comments, empty lines etc.
            outputLines.append(line)
            pos += 1
        
        if not remainingOptionsWritten:
            # Write remaining options. If there is a subsection in the file we've done this already 
            for option in section.getOptions():
                if option.name not in writtenOptions:
                    self._writeOption(option, outputLines)
        
        # Write remaining subsections
        for subsection in section.getSubsections():
            if subsection.name not in writtenSubsections:
                self._writeSection(subsection, depth+1, outputLines)
            
        if all(len(line.strip()) == 0 for line in outputLines[startLen:]): 
            # nothing written except section header => do not write anything at all for this section
            # Remove empty lines together with section header
            if len(outputLines) > 0:
                del outputLines[startLen-1:]
        elif len(outputLines[-1].strip()) > 0:
             # add an empty line after each section, but first check if there is already one
            outputLines.append('')
            
        return pos
    
    def _isValueCorrect(self, option, string):
        """Check whether the given string is parsed to the value of the given option.""" 
        try:
            value = option.parseString(string)
            return value == option.value # ignore temporary values
        except:
            return False
        
    def _writeOption(self, option, outputLines):
        """If the option value differs from its default value, add a line to *outputLines*."""
        if option.value != option.default:
            if option.type == bool:
                value = "True" if option.value else "False"
            elif option.type == list:
                if len(option.value) == 0:
                    value = ""
                value = ", ".join(str(v) for v in option.value)
            else: value = str(option.value)
            
            outputLines.append('{} = {}'.format(option.name, value))

    def _writeSection(self, section, depth, outputLines):
        """Write the given section to *outputLines*. *depth* is the depth of the section, i.e. the number of
        opening brackets in its title line. Contrary to ''_compareAndWriteSection'' this simply writes the
        section without comparing to values that are already present, keeping comments or other complicated
        stuff. This is used for sections that are not present in the file.
        """
        outputLines.append('['*depth+section.name+']'*depth)
        startLen = len(outputLines)
        
        for option in section.getOptions():
            self._writeOption(option, outputLines)
            
        for subsection in section.getSubsections():
            self._writeSection(subsection, depth+1, outputLines)
            
        if len(outputLines) == startLen:
            # nothing written except section header => do not write anything at all for this section
            del outputLines[-1]
        else: outputLines.append('') # add an empty line after each section
        
registerConfigType("config", ConfigFile)


class JsonFile(File):
    """This class represents configuration files of type 'json'."""
    def _read(self):
        """Read a storage file at the given path and return whatever is contained in it. Return an empty dict
        when the file does not exist.
        """
        if os.path.exists(self.path):
            import json
            try:
                with open(self.path, 'r') as file:
                    result = json.load(file, object_pairs_hook=collections.OrderedDict)
                    if not isinstance(result, dict):
                        raise ConfigError("Config file does not contain a dict.")
                    return result
            except Exception as e:
                raise ConfigError(str(e))
        else:
            return {}

    def _write(self):
        import json
        rawDict = self.section._toRawDict()
        assert rawDict is not None
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            # Do not write the file directly because all contents will be lost if rawDict 
            # contains an object that is not serializable.
            string = json.dumps(rawDict, ensure_ascii=False, indent=4)
            with open(self.path, 'w+') as file:
                file.write(string)
        except Exception as e:
            raise ConfigError(str(e))

registerConfigType("json", JsonFile)


class PickleFile(File):
    """This class represents configuration files of type 'pickle'."""
    def _read(self):
        if os.path.exists(self.path):
            import pickle
            try:
                with open(self.path, 'rb') as file:
                    result = pickle.load(file)
                    if not isinstance(result, dict):
                        raise ConfigError("Config file does not contain a dict.")
                    return result
            except Exception as e:
                raise ConfigError(str(e))
        else:
            return {}

    def _write(self):
        import pickle
        rawDict = self.section._toRawDict()
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            pickle.dump(rawDict, open(self.path, "wb"))
        except Exception as e:
            raise ConfigError(str(e))
        
registerConfigType("pickle", PickleFile)
    
        
class Access:
    """An Access-object wraps a File to provide easy access to the actual configuration values (by-passing
    instances of Option and Section). On attribute access or item access it will directly return the option's
    value or -- when accessing a subsection -- an Access-object wrapping the subsection.
    """
    def __init__(self, file, section):
        self._file = file
        self._section = section

    def __getattr__(self, name):
        result = self._section.members[name]
        if isinstance(result, Option):
            return result.getValue()
        else: return Access(self._file, result)

    def __setattr__(self, name, value):
        if name in ['_section', '_file']:
            super().__setattr__(name, value)
        else:
            option = self._section.members[name]
            if isinstance(option, Option):
                option.setValue(value)
            else: raise KeyError("'{}' is a section, not an option.".format(name))

    def __getitem__(self,key):
        result = self._section.members[key]
        if isinstance(result, Option):
            return result.getValue()
        else: return Access(self._file, result)

    def __setitem__(self, key, value):
        option = self._section.members[key]
        if isinstance(option, Option):
            option.setValue(value)
        else: raise KeyError("'{}' is a section, not an option.".format(name))


def _pprintSection(self, section, nesting=1):
    """Helper for pprint: Pretty-print a section."""
    print(("    "*(nesting-1)) + ('['*nesting) + section.name+(']'*nesting))
    for member in section.members.values():
        if isinstance(member, Section):
            print()
            _pprintSection(member, nesting+1)
        else: print("{}{}: {}".format("    "*(nesting-1), member.name, member.getValue()))
    print() # empty line
    