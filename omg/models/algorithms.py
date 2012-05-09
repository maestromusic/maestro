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
"""This module contains algorithms that operate on Elements."""

def groupAndSort(elements):
    """Takes a list of *Element* instances, groups them by their parent pointer,
    removes duplicates, and sorts them according to their *position*.
    Returns a dict mapping parent ids to sorted lists of children.
    """
    result = dict()
    for element in element:
        pid = element.parent.id
        if pid not in result:
            result[pid] = []
        there = False
        for other in result[pid]:
            if other.id == element.id and other.iPosition() == element.iPosition():
                there = True
        if not there:
            result[pid].append(element)
    for v in result.values():
        v.sort(key = lambda element: element.position)
    return result
        
    