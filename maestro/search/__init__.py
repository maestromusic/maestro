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
                