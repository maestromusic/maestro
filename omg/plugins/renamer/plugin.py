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
from omg import logging

logger = logging.getLogger(__name__)

def defaultStorage():
    return {"SECTION:renamer":
            {'profiles': ("default", "<artist>") } }

def enable():
    pass
    


 
import pyparsing
from pyparsing import Forward, Literal, OneOrMore, Optional, Word, alphas, alphanums, nums, printables

lbrace = Literal("<").suppress()
rbrace = Literal(">").suppress()

number = Word(nums)
levelDef = number + Literal(".").suppress()

tagName = Word(alphas + "_", alphanums + "_:()/\\")

tagMacro = lbrace + Optional(levelDef("levelDef")) + tagName("tag") + rbrace

expression = Forward()

ifExpr = Literal("?").suppress() + expression

condition = (lbrace + tagName("tag") + ifExpr("if") + rbrace)("condition")
staticText = pyparsing.CharsNotIn("<>")#Word("".join(p for p in printables if p not in "<>"))
expression << OneOrMore(tagMacro | staticText | condition)
def tagMacroAction(s, loc, toks):
    macro = toks["tag"]
    if "levelDef" in toks:
        level = int(toks["levelDef"][0])
        if level > len(currentParents):
            return [""]
        pos,parent = currentParents[-level]
        elemTag = parent.tags
    else:
        elemTag = currentElem.tags
    if tags.exists(macro.lower()):
        tag = tags.get(macro.lower())
        if tag in elemTag:
            return [",".join(elemTag[tag])]
tagMacro.setParseAction(tagMacroAction)

def conditionAction(s, loc, toks):
    print('if {} then eval {}'.format(toks["tag"], toks["if"]))
condition.setParseAction(conditionAction)
def traverse(element, *parents):
    global currentElem, currentParents
    currentElem = element
    currentParents = parents
    if element.isFile():
        print(expression.parseString("<title>/<composer?<composer>>"))
    else:
        for pos, childId in element.contents.items():
            child = levels.real.get(childId)
            traverse(child, (pos, element), *parents)
traverse(levels.real.get(23))
logger.info("renamer enabled")


def disable():
    pass