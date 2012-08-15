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
This module will really modify database and filesystem (using database.write and realfiles). It does not
do any Undo-/Redo-stuff.
"""

import os
 
from .. import database as db, logging, utils, filebackends

logger = logging.getLogger(__name__)

    
def changeContents(changes):
    """Change content relations of containers. *changes* is a dict mapping container ID to (oldContents, newContents)
    tuples of ContentList instances.""" 
    idsWithPriorContents = [ id for id,changeTup in changes.items() if len(changeTup[0]) > 0 ]
    if len(idsWithPriorContents) > 0:
        # first remove old content relations
        db.write.removeAllContents(idsWithPriorContents)
    tuples = []
    for containerId, (_, newContents) in changes.items():
        tuples.extend( ( (containerId,) + x) for x in newContents.items())
    db.write.addContents(tuples)
    
def changeTags(changes, reverse = False):
    """Change tags of files in database. *changes* is a mapping from ids to
    TagDifference objects. If *reverse* is True, changes are made reverted rather than applied."""
    
    removeTuples = []
    addTuples = []
    neededValues = set()
    for id, tagDiff in changes.items():
        for tag, values in (tagDiff.removals if not reverse else tagDiff.additions):
            removeTuples.extend( (id, tag.id, db.idFromValue(tag, value)) for value in values)
        for tag, values in (tagDiff.additions if not reverse else tagDiff.removals):
            addTuples.extend( (id, tag.id, value) for value in values)
            neededValues.update(( (tag, value) for value in values ))
    if len(removeTuples) > 0:
        db.write.removeTagValuesMulti(removeTuples)
    neededValues = list(neededValues)
    db.write.makeValueIDs(neededValues)
    addData = []
    for id, tagId, value in addTuples:
        addData.append( (id, tagId, db.idFromValue(tagId, value)))
    if len(addData) > 0:
        db.write.addTagValuesMulti(addData)
    
def changeFlags(changes, reverse = False):
    removeTuples = []
    addTuples = []
    for id, flagDiff in changes.items():
        addTuples.extend( (id,flag.id) for flag in flagDiff.additions)
        removeTuples.extend( (id,flag.id) for flag in flagDiff.removals)
    if reverse:
        addTuples, removeTuples = removeTuples, addTuples
    if len(addTuples) > 0:
        db.write.addFlags(addTuples)
    if len(removeTuples) > 0:
        db.write.removeFlags(removeTuples)

def changeFileTags(url, tagDiff, reverse = False):
    file = filebackends.get(url)
    if reverse:
        tagDiff.revert(file.tags, False)
    else:
        tagDiff.apply(file.tags, False)
    file.save()
