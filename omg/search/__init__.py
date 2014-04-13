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

from . import criteria
from .. import database as db, config
from ..core import tags

# Name of the temporary search table
# The table is created in the search thread and temporary, so that it does not conflict with other threads.
TT_HELP = 'tmp_help'


def init():
    """Initialize the search module."""
    criteria.SEARCH_TAGS = set()
    for tagname in config.options.tags.search_tags:
        if tags.isInDb(tagname):
            criteria.SEARCH_TAGS.add(tags.get(tagname))
    if db.type == 'mysql':
        db.query("""
            CREATE TEMPORARY TABLE IF NOT EXISTS {} (
                value_id MEDIUMINT UNSIGNED NOT NULL,
                tag_id MEDIUMINT UNSIGNED NULL,
                INDEX(value_id, tag_id))
                CHARACTER SET 'utf8'
            """.format(TT_HELP))
    else:
        db.query("""
            CREATE TABLE IF NOT EXISTS {} (
                value_id  MEDIUMINT UNSIGNED NOT NULL,
                tag_id MEDIUMINT UNSIGNED NULL)
            """.format(TT_HELP))
        db.query("CREATE INDEX IF NOT EXISTS {0}_idx ON {0} (value_id, tag_id)".format(TT_HELP))


def search(searchCriterion, abortSwitch=None):
    """Process the given search criterion. Store the results in the attribute 'result' of the criterion.
    If *abortSwitch* is given, it is called during the algorithm. By throwing an exception in abortSwitch,
    this provides a way to abort a running search."""
    for criterion in searchCriterion.getCriteriaDepthFirst():
        if not isinstance(criterion, criteria.MultiCriterion):
            for queryData in criterion.getQueries(db.prefix+"elements"):
                #print(queryData)
                if isinstance(queryData, str):
                    result = db.query(queryData)
                else: result = db.query(*queryData)
                #print(list(db.query("SELECT value FROM new_values_varchar WHERE id IN (SELECT value_id FROM tmp_help)").getSingleColumn()))
                if abortSwitch is not None:
                    abortSwitch()
            criterion.result = set(result.getSingleColumn())
        else:
            #TODO: implement MultiCriterions more efficiently
            # If the first criterion in an AND-criterion returns only a small set,
            # this could be used to make the second criterion faster.
            if criterion.junction == 'AND':
                method = criterion.criteria[0].result.intersection
            else: method = criterion.criteria[0].result.union
            criterion.result = method(*[crit.result for crit in criterion.criteria[1:]])
            if criterion.negate:
                allElements = set(db.query("SELECT id FROM {p}elements").getSingleColumn())
                criterion.result = allElements - criterion.result
            if abortSwitch is not None:
                abortSwitch()

    assert searchCriterion.result is not None
    return searchCriterion.result
