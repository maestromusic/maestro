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


import pyparsing
from pyparsing import Forward, Literal, OneOrMore, Optional, Word, alphas, alphanums, nums

from PyQt5 import QtCore

translate = QtCore.QCoreApplication.translate

from ...core import tags
from ... import config, profiles

    
def defaultStorage():
    return {"renamer": {'profiles': [],
                        'current_profile': None
                        }
            }

def defaultConfig():
    return {"renamer": {
            "positionDigits": (int,2,"Minimum number of digits to use for positions (filled with zeros).")
        }}


profileCategory = None


def enable():
    global profileCategory
    profileCategory = profiles.ProfileCategory("renamer",
                                               translate("Renamer","Renamer"),
                                               config.getOption(config.storage, 'renamer.profiles'),
                                               profileClass=GrammarRenamer,
                                               iconName='edit-rename')
    profiles.manager.addCategory(profileCategory)
    
    from .gui import RenameFilesAction
    from maestro.widgets.editor import editor
    from maestro.widgets import browser
    RenameFilesAction.register('renamer', context='plugins',
                               shortcut=translate('RenameFilesAction', 'Ctrl+R'))
    editor.EditorTreeView.addActionDefinition('renamer')
    browser.BrowserTreeView.addActionDefinition('renamer')


def disable():
    from maestro.gui import actions
    actions.manager.unregisterAction('renamer')
    global profileCategory
    profiles.manager.removeCategory(profileCategory)
    profileCategory = None


class FormatSyntaxError(SyntaxError):
    pass


class GrammarRenamer(profiles.Profile):

    def __init__(self, name, type=None, state=None):
        super().__init__(name, type)
        self.positionFormat = "{:0>" + str(config.options.renamer.positionDigits) + "}"
        self.read(state)

    def levelDefAction(self, s, loc, toks):
        level = int(toks[0])
        return [level]
       
    def tagDefinitionAction(self, s, loc, toks):
        macro = toks["tag"]
        ret = toks.copy()
        ret["exists"] = False
        ret["value"] = None
        if "levelDef" in toks:
            level = toks["levelDef"][0]
            if level > len(self.currentParents):
                ret["value"] = ""
                return ret
            pos,parent = self.currentParents[-level]
            if macro == "#":
                ret["value"] =  self.positionFormat.format(pos)
            else:
                elemTag = parent.tags
        else:
            elemTag = self.currentElem.tags
            if macro == "#":
                if len(self.currentParents) > 0:
                    ret["value"] = self.positionFormat.format(self.currentParents[0][0])
        if macro != "#":
            if tags.isInDb(macro.lower()):
                tag = tags.get(macro.lower())
                if tag in elemTag:
                    ret["value"] = ",".join(map(str, elemTag[tag])).translate(self.translation)
        ret["exists"] = (ret["value"] != None)
        if ret["value"] is None:
            ret["value"] = ""
        return ret
    
    def conditionAction(self, s, loc, toks):
        tag = toks.tagDef
        if "if" in toks or "else" in toks:
            if tag.exists:
                ret = toks["if"] if "if" in toks else []
            else:
                ret = toks["else"] if "else" in toks else []
        else: ret = tag.value
        return ret

    def read(self, state):
        if state is None:
            state = {}
        self.formatString = state.get('formatString', '/tmp/<1.artist>/<1.title>/<#> - <title>')
        self.replaceChars = state.get('replaceChars', '\\:/')
        self.replaceBy = state.get('replaceBy', '_.;')
        self.removeChars = state.get('removeChars','?*')
        
        if len(self.replaceChars) != len(self.replaceBy):
            raise ValueError("replaceChars and replaceBy must equal in length")
        self.translation = str.maketrans(self.replaceChars, self.replaceBy, self.removeChars)
        
        oldDefaultWhitespaceChars = pyparsing.ParserElement.DEFAULT_WHITE_CHARS    
        pyparsing.ParserElement.setDefaultWhitespaceChars("\t\n")
        #pyparsing.ParserElement.enablePackrat() does not work (buggy)
        lbrace = Literal("<").suppress()
        rbrace = Literal(">").suppress()
        
        number = Word(nums)
        
        levelDef = number + Literal(".").suppress()
        levelDef.setParseAction(self.levelDefAction)
        
        tagName = Word(alphas + "_", alphanums + "_:()/\\")
        
        tagDefinition = Optional(levelDef("levelDef")) + (tagName | "#")("tag") 
        tagDefinition.setParseAction(self.tagDefinitionAction)
        
        expression = Forward()
        
        ifExpr = Literal("?").suppress() + expression
        elseExpr = Literal("!").suppress() + expression
        condition = lbrace + tagDefinition("tagDef") \
                + ((Optional(ifExpr("if")) + Optional(elseExpr("else"))) | (Optional(elseExpr("else")) + Optional(ifExpr("else"))))\
                + rbrace # i am sure this is possible in a nicer way ...
        condition.setParseAction(self.conditionAction)
        
        staticText = pyparsing.CharsNotIn("<>!?")#Word("".join(p for p in printables if p not in "<>"))
        expression << OneOrMore(condition | staticText)
        self.expression = expression
        pyparsing.ParserElement.setDefaultWhitespaceChars(oldDefaultWhitespaceChars)
    
    def save(self):
        return dict(formatString=self.formatString, replaceChars=self.replaceChars,
                    replaceBy=self.replaceBy, removeChars=self.removeChars)
    
    def computeNewPath(self):
        """Computes the new path for the element defined by *self.currentElem* and *self.currentParents*."""
        extension = self.currentElem.url.extension
        try:
            return  "".join(map(str, self.expression.parseString(self.formatString))) + "." + extension
        except pyparsing.ParseException as e:
            raise FormatSyntaxError(str(e))
        
    def traverse(self, element, *parents):
        self.currentElem = element
        self.currentParents = parents
        if element.isFile():
            self.result[element] = self.computeNewPath()
        else:
            for pos, childId in element.contents.items():
                self.traverse(self.level.collect(childId), (pos, element), *parents)
        
    def renameContainer(self, level, element):
        self.result = dict()
        self.level = level
        self.traverse(element)
        return self.result

    @classmethod
    def configurationWidget(cls, profile, parent):
        from . import gui
        return gui.GrammarConfigurationWidget(profile=profile, parent=parent)
    
    def __neq__(self, other):
        if not isinstance(other, GrammarRenamer):
            return True
        return self.formatString != other.formatString or \
               self.replaceChars != other.replaceChars or \
               self.replaceBy != other.replaceBy or \
               self.removeChars != other.removeChars

    def __eq__(self, other):
        return not self.__neq__(other)
    
    def __hash__(self):
        return id(self)
        