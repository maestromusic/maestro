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


from omg.core import tags, levels
from omg import logging, config, profiles

logger = logging.getLogger(__name__)

import pyparsing
from pyparsing import Forward, Literal, OneOrMore, Optional, Word, alphas, alphanums, nums
    
def defaultStorage():
    return {"SECTION:renamer":
            {'profiles': ("default", "<artist>") } }

def defaultConfig():
    return {"renamer": {
            "positionDigits": (int,2,"Minimum number of digits to use for positions (filled with zeros).")
        }}

initialized = False
def enable():
    if not initialized:
        init()
    from .gui import RenameFilesAction
    from omg.gui import editor, browser
    editor.EditorTreeView.actionConfig.addActionDefinition((("plugins", 'renamer'),), RenameFilesAction)
    browser.BrowserTreeView.actionConfig.addActionDefinition((("plugins", 'renamer'),), RenameFilesAction)
class GrammarRenamer(profiles.Profile):
        
    name = "GrammarRenamer"
    def levelDefAction(self, s, loc, toks):
        level = int(toks[0])
        return [level]
       
    def tagDefinitionAction(self, s, loc, toks):
        macro = toks["tag"]
        ret = toks.copy()
        ret["exists"] = False
        ret["value"] = None
        if "levelDef" in toks:
            #print('levelDef: {}'.format(toks["levelDef"]["level"]))
            level = toks["levelDef"][0]
            if level > len(self.currentParents):
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
            if tags.exists(macro.lower()):
                tag = tags.get(macro.lower())
                if tag in elemTag:
                    ret["value"] = ",".join(map(str, elemTag[tag])).replace("/", "-")
        ret["exists"] = (ret["value"] != None)
        if ret["value"] is None:
            ret["value"] = ""
        return ret
    
    def conditionAction(self, s, loc, toks):
        tag = toks.tagDef
        if "if" in toks or "else" in toks:
            if tag.exists:
                return toks["if"] if "if" in toks else []
            else:
                return toks["else"] if "else" in toks else []
        else: return tag.value
    
    def __init__(self, name, formatString = ""):
        super().__init__(name)
        
        # grammar definition
        self.positionFormat = "{:0>" + str(config.options.renamer.positionDigits) + "}"
        self.formatString = formatString
        pyparsing.ParserElement.setDefaultWhitespaceChars("\t\n")
        lbrace = Literal("<").suppress()
        rbrace = Literal(">").suppress()
        
        number = Word(nums)
        
        levelDef = number + Literal(".").suppress()
        levelDef.setParseAction(self.levelDefAction)
        
        tagName = Word(alphas + "_", alphanums + "_:()/\\")
        
        tagDefinition = Optional(levelDef("levelDef")) + (tagName ^ "#")("tag") 
        tagDefinition.setParseAction(self.tagDefinitionAction)
        
        expression = Forward()
        
        ifExpr = Literal("?").suppress() + expression
        elseExpr = Literal("!").suppress() + expression
        condition = lbrace + tagDefinition("tagDef") \
                + ((Optional(ifExpr("if")) + Optional(elseExpr("else"))) ^ (Optional(elseExpr("else")) + Optional(ifExpr("else"))))\
                + rbrace # i am sure this is possible in a nicer way ...
        condition.setParseAction(self.conditionAction)
        
        staticText = pyparsing.CharsNotIn("<>!?")#Word("".join(p for p in printables if p not in "<>"))
        expression << OneOrMore(staticText | condition)
        self.expression = expression
    
    def computeNewPath(self):
        """Computes the new path for the element defined by *self.currentElem* and *self.currentParents*."""
        extension = self.currentElem.path.rsplit(".", 1)[1]
        return "".join(self.expression.parseString(self.formatString)) + "." + extension
        
    def traverse(self, element, *parents):
        self.currentElem = element
        self.currentParents = parents
        if element.isFile():
            self.result[element.id] = self.computeNewPath()
        else:
            for pos, childId in element.contents.items():
                self.traverse(levels.real.get(childId), (pos, element), *parents)
        
    def renameContainer(self, id):
        self.result = dict()
        self.traverse(levels.real.get(id))
        return self.result

def init():
    

    global profileConfig
    profileConfig = profiles.ProfileConfiguration("renamer", config.options.renamer, [GrammarRenamer])
    global initialized
    initialized = True
    logger.debug("initialized renamer plugin")


def disable():
    editor.EditorTreeView.actionConfig.removeActionDefinition((("plugins", 'renamer'),))