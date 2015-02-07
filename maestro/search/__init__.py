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
#

from . import criteria
from .. import database as db, config, utils
from ..core import tags

# Name of the temporary search table
# The table is created in the search thread and temporary, so that it does not conflict with other threads.
TT_HELP = db.prefix+'tmp_help'


def init():
    """Initialize the search module."""
    # Using temporary tables is important when several (worker) threads use the search function
    # at the same time: With temporary tables each thread has its own help table.
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


def search(searchCriterion, domain=None):
    """Process the given search criterion. Store the results in the attribute 'result' of the criterion."""
    SearchTask(searchCriterion, domain).processImmediately()


class SearchTask(utils.worker.Task):
    def __init__(self, criterion, domain):
        self.criterion = criterion
        self.domain = domain
        
    def process(self):
        import time
        start = time.perf_counter()
        for criterion in self.criterion.getCriteriaDepthFirst():
            if not isinstance(criterion, criteria.MultiCriterion):
                generator = criterion.process(db.prefix+"elements", self.domain)
                if generator is not None:
                    yield from generator
                else: yield
            else:
                #TODO: implement MultiCriterions more efficiently
                # If the first criterion in an AND-criterion returns only a small set,
                # this could be used to make the second criterion faster.
                if criterion.junction == 'AND':
                    method = criterion.criteria[0].result.intersection
                else: method = criterion.criteria[0].result.union
                criterion.result = method(*[crit.result for crit in criterion.criteria[1:]])
                if criterion.negate:
                    if self.domain is not None:
                        query = "SELECT id FROM {p}elements WHERE domain={}".format(self.domain.id)
                    else: query = "SELECT id FROM {p}elements"
                    allElements = set(db.query(query).getSingleColumn())
                    criterion.result = allElements - criterion.result
                yield
        end = time.perf_counter()
                