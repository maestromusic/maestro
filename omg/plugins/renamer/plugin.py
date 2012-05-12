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
from omg import logging, config

logger = logging.getLogger(__name__)

def defaultStorage():
    return {"SECTION:renamer":
            {'profiles': ("default", "<artist>") } }

def defaultConfig():
    return {"renamer": {
            "positionDigits": (int,2,"Minimum number of digits to use for positions (filled with zeros).")
        }}

def enable():
    init()
    


def init():
    import pyparsing
    from pyparsing import Each, Forward, Literal, OneOrMore, Optional, Word, alphas, alphanums, nums, printables
    
    positionFormat = "{:0>" + str(config.options.renamer.positionDigits) + "}"
    pyparsing.ParserElement.setDefaultWhitespaceChars("\t\n")
    lbrace = Literal("<").suppress()
    rbrace = Literal(">").suppress()
    
    number = Word(nums)
    
    levelDef = number + Literal(".").suppress()
    def levelDefAction(s, loc, toks):
        level = int(toks[0])
        return [level]
    levelDef.setParseAction(levelDefAction)
    
    tagName = Word(alphas + "_", alphanums + "_:()/\\")
    
    tagDefinition = Optional(levelDef("levelDef")) + (tagName ^ "#")("tag") 
    def tagDefinitionAction(s, loc, toks):
        macro = toks["tag"]
        ret = toks.copy()
        ret["exists"] = False
        ret["value"] = None
        if "levelDef" in toks:
            #print('levelDef: {}'.format(toks["levelDef"]["level"]))
            level = toks["levelDef"][0]
            if level > len(currentParents):
                return ret
            pos,parent = currentParents[-level]
            if macro == "#":
                ret["value"] =  positionFormat.format(pos)
            else:
                elemTag = parent.tags
        else:
            elemTag = currentElem.tags
            if macro == "#":
                if len(currentParents) > 0:
                    ret["value"] = positionFormat.format(currentParents[0][0])
        if macro != "#":
            if tags.exists(macro.lower()):
                tag = tags.get(macro.lower())
                if tag in elemTag:
                    ret["value"] = ",".join(map(str, elemTag[tag])).replace("/", "-")
        ret["exists"] = (ret["value"] != None)
        if ret["value"] is None:
            ret["value"] = ""
        return ret
        
    tagDefinition.setParseAction(tagDefinitionAction)
    
    expression = Forward()
    
    ifExpr = Literal("?").suppress() + expression
    elseExpr = Literal("!").suppress() + expression
    condition = lbrace + tagDefinition("tagDef") \
            + ((Optional(ifExpr("if")) + Optional(elseExpr("else"))) ^ (Optional(elseExpr("else")) + Optional(ifExpr("else"))))\
            + rbrace # i am sure this is possible in a nicer way ...
    def conditionAction(s, loc, toks):
        tag = toks.tagDef
        if "if" in toks or "else" in toks:
            if tag.exists:
                return toks["if"] if "if" in toks else []
            else:
                return toks["else"] if "else" in toks else []
        else: return tag.value
    
    condition.setParseAction(conditionAction)
    
    staticText = pyparsing.CharsNotIn("<>!?")#Word("".join(p for p in printables if p not in "<>"))
    expression << OneOrMore(staticText | condition)
    
    
    def traverse(element, format, *parents):
        global currentElem, currentParents
        currentElem = element
        currentParents = parents
        if element.isFile():
            extension = element.path.rsplit(".", 1)[1]
            return [(element.id, "".join(expression.parseString(format)) + "." + extension)]
        else:
            ret = []
            for pos, childId in element.contents.items():
                ret.extend(traverse(levels.real.get(childId), format, (pos, element), *parents))
            return ret
            
    def renameContainer(id, format):
        result = traverse(levels.real.get(id), format)
        for id, newPath in result:
            print("{}->{}".format(levels.real.get(id).path, newPath))
    format="""
<composer?Klassik/<composer>/<album> (<artist>)/<#> - <title>
!Modern/<artist>/<date?<date> - ><album>/<#> - <title>>""" 
    renameContainer(12, format)
    logger.info("renamer enabled")


def disable():
    pass