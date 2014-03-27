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
 
import re, collections, json, os

from .. import logging

logger = logging.getLogger(__name__)

# Pattern to match section headers, normal lines and empty lines/comments in the config files
sectionPattern = re.compile('\s*(\[+)([^\]]+)(\]+)\s*$')
linePattern = re.compile('([^=]+)=(.*)$')
ignorePattern = re.compile('\s*(#.*)?$')


class ConfigError(Exception):
    """A ConfigError is for example raised if the config file contains invalid syntax."""
    def __init__(self, message):
        self.message = message
    
    def __str__(self):
        return "ConfigError: {}".format(self.message)


def readConfig(path):
    """Read a configuration file at the specified path and return a raw dict containing the option values.
    Return an empty dict when the file does not exist.
    """
    try:
        if not os.path.exists(path):
            return {}
        with open(path,'r') as file:
            lines = [line.rstrip() for line in file.readlines()]
    except:
        raise ConfigError("Cannot read config file")
    
    config = collections.OrderedDict()
    sections = [config]
    for lineNumber,line in enumerate(lines):
        currentSection = sections[-1]
        if ignorePattern.match(line):
            continue
        
        matchObj = sectionPattern.match(line)
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
                                  "the same name (line {}).".format(name,lineNumber))
            currentSection[name] = collections.OrderedDict()
            sections.append(currentSection[name])
            continue
        
        matchObj = linePattern.match(line)
        if matchObj is not None:
            name = matchObj.group(1).strip()
            value = matchObj.group(2).strip()
            if name in currentSection:
                logger.warning("Option '{}' appears twice (linenumber {})".format(name,lineNumber))
            currentSection[name] = value
            continue
            
        # Neither pattern matched
        raise ConfigError("Syntax error in line {}".format(lineNumber))
            
    return config
    

def writeConfig(path,config):
    """Write the config section *config* to the given path. Be clever and try to change as little as possible
    of user-edited lines (i.e. keep comments, order etc.). For this read the file and compare values with
    the values from *config*.
    """
    outputLines = [] # these lines, joined by \n, will form the final file
    try:
        if not os.path.exists(path):
            inputLines = []
        else:
            with open(path,'r') as file:
                inputLines = [line.rstrip() for line in file.readlines()]
    except:
        raise ConfigError("Cannot read config file")
    
    _compareAndWriteSection(config,0,inputLines,0,outputLines)
    
    # Debug
    #print('\n'.join(outputLines))
    #return
    
    try:
        with open(path,'w') as file:
            file.write('\n'.join(outputLines))
    except:
        raise ConfigError("Cannot write config file")
    
    
def _compareAndWriteSection(section,depth,inputLines,pos,outputLines):
    """Starting at position *pos*, read the input lines, compare the values within to the values from
    *section* and append output lines (keeping comments or lines with unchanged values, adding changed values
    etc.). Handle subsections recursively. *depth* is the depth of section (the number of opening brackets in
    its title line.
    """
    from . import ConfigOption, Section
    writtenOptions = []
    writtenSubsections = []
    # Before the first subsection we must write all options
    remainingOptionsWritten = False
    
    if section.name != '<Main>':
        outputLines.append('['*depth+section.name+']'*depth)
    startLen = len(outputLines)
    
    while pos < len(inputLines):
        line = inputLines[pos]
        
        # Handle option lines
        matchObj = linePattern.match(line)
        if matchObj is not None:
            name = matchObj.group(1).strip()
            value = matchObj.group(2).strip()
            if name not in section.members.keys() or not isinstance(section.members[name],ConfigOption):
                # unknown option, keep it
                outputLines.append(line)
            else:
                option = section.members[name]
                if _isValueCorrect(option,value):
                    outputLines.append(line)
                else: _writeOption(option,outputLines)
                writtenOptions.append(option.name)
            pos += 1
            continue
        
        # Handle section lines
        matchObj = sectionPattern.match(line)
        if matchObj is not None:
            if not remainingOptionsWritten:
                remainingOptionsWritten = True
                for option in section.getOptions():
                    if option.name not in writtenOptions:
                        _writeOption(option,outputLines)
            sectionDepth = len(matchObj.group(1))
            name = matchObj.group(2).strip()
            if sectionDepth == depth + 1 and name in section.members \
                    and isinstance(section.members[name],Section):
                # this is a subsection
                pos = _compareAndWriteSection(section.members[name],sectionDepth,inputLines,pos+1,outputLines)
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
                _writeOption(option,outputLines)
    
    # Write remaining subsections
    for subsection in section.getSubsections():
        if subsection.name not in writtenSubsections:
            _writeSection(subsection,depth+1,outputLines)
        
    if all(_isEmpty(line) for line in outputLines[startLen:]): 
        # nothing written except section header => do not write anything at all for this section
        # Remove empty lines together with section header
        if len(outputLines) > 0:
            del outputLines[startLen-1:]
    elif not _isEmpty(outputLines[-1]):
         # add an empty line after each section, but first check if there is already one
        outputLines.append('')
        
    return pos
    

def _isValueCorrect(option,string):
    """Check whether the given string is parsed to the value of the given option.""" 
    try:
        value = option.parseString(string)
        return value == option.getValue(temp=False)
    except:
        return False
    
    
def _writeOption(option,outputLines):
    """If the option value differs from its default value, add a line to *outputLines*."""
    if option.value != option.default:
        outputLines.append('{} = {}'.format(option.name,option.export()))


def _writeSection(section,depth,outputLines):
    """Write the given section to *outputLines*. *depth* is the depth of the section, i.e. the number of
    opening brackets in its title line. Contrary to ''_compareAndWriteSection'' this simply writes the
    section without comparing to values that are already present, keeping comments or other complicated
    stuff. This is used for sections that are not present in the file.
    """
    outputLines.append('['*depth+section.name+']'*depth)
    startLen = len(outputLines)
    
    for option in section.getOptions():
        _writeOption(option,outputLines)
        
    for subsection in section.getSubsections():
        _writeSection(subsection,depth+1,outputLines)
        
    if len(outputLines) == startLen:
        # nothing written except section header => do not write anything at all for this section
        del outputLines[-1]
    else: outputLines.append('') # add an empty line after each section


def readStorage(path):
    """Read a storage file at the given path and return whatever is contained in it. Return an empty dict
    when the file does not exist.
    """
    try:
        if not os.path.exists(path):
            return {}
        with open(path,'r') as file:
            return json.load(file,object_pairs_hook=collections.OrderedDict)
    except Exception as e:
        raise ConfigError(str(e))


def writeStorage(path,storage):
    """Write the given storage section to a file at the given path."""
    rawDict = storage._toRawDict()
    try:
        # Do not write the file directly because all contents will be lost if rawDict contains an object
        # that is not serializable.
        string = json.dumps(rawDict,ensure_ascii=False,indent=4)
        with open(path,'w+') as file:
            file.write(string)
    except Exception as e:
        raise ConfigError(str(e))

def _isEmpty(string):
    """Check whether *string* is empty or contains only spaces."""
    # ''.isspace() is False
    return len(string) == 0 or string.isspace()
