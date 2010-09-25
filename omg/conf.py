# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

import os, logging
from . import constants

logger = logging.getLogger("conf")


class ConfigError(Exception):
    
    def __init__(self, msg):
        self.message = msg
        
class ConfigOption:
    
    def __init__(self, type, default):
        self.type = type
        self.default = default
        self.value = default
        self.fileValue = default
    
    def updateValue(self, value, updateFileValue = False):
        if not isinstance(value, self.type):
            if self.type in (int, str, bool):
                value = self.type(value)
            elif self.type == list and isinstance(value, str):
                value = map(lambda x: x.split(" \t"), value.split(","))
            else:
                raise ConfigError("Type of {} does not match type of this option and can't be converted")
        self.value = value
        if updateFileValue:
            self.fileValue = value

class ConfigSection:
    
    def __init__(self, name):
        self.options = []
        self.name = name
    
    def __getattr__(self, attr):
        if attr in self.options:
            return self.options[attr]
        else:
            raise AttributeError("Section {} has no option {}".format(self.name, attr))
    
    def addOption(self, name, type, default):
        self.options[name] = ConfigOption(type, default)
        
class Config:
    
    def __init__(self):
        self.sections = {}
        
    def __getattr__(self, section):
        if section in self.sections:
            return self.sections[section]
        else:
            raise AttributeError("Section {} does not exist".format(section))
    
    def readFromFile(self, filename):
        with open(filename, "r") as file:
            section = "default"
            i = 1
            for line in file.readlines():
                i += 1
                line = line.strip(" \t")
                if line[0] == "#": #comment line
                    continue
                if line[0] == "[" and line[-1] == "]":
                    section = line[1:-1].strip(" \t")
                    if not section in self.sections:
                        raise ConfigError("File {} tries to access section {} which does not exist".format(filename, section))
                    continue
                try:
                    name, value = (x.strip(" \t") for x in line.split("=", 1))
                except ValueError:
                    raise ConfigError("Syntax error in line {} of file {}".format(i, file))
                self.sections[section][name].updateValue(value, True)
                        
    
    def addOption(self, section, name, type, default):
        if section in self.sections:
            sect = self.sections[section]
        else:
            sect = self.sections[section] = ConfigSection(section)
        sect.addOption(type, default)
        

c = Config()
def init():
    c.readFromFile(constants.CONFIG)