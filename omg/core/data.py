# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2012-2013 Martin Altmayer, Michael Helmling
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

class DataDifference:
    """Efficiently stores the difference between two data attributes of elements.
    """
    
    def __init__(self, dataA, dataB):
        self.diffs = {}
        if dataA is None:
            dataA = {}
        if dataB is None:
            dataB = {}
        for key in set(dataA.keys()) | set(dataB.keys()):
            a = dataA[key] if key in dataA else None
            b = dataB[key] if key in dataB else None
            if a != b:
                self.diffs[key] = (a, b)
            
    def apply(self, element):
        for key, (_, b) in self.diffs.items():
            if b is None:
                del element.data[key]
            else:
                element.data[key] = b
                
    def revert(self, element):
        for key, (a, _) in self.diffs.items():
            if a is None:
                del element.data[key]
            else:
                element.data[key] = a
                
    def inverse(self):
        ret = DataDifference(None, None)
        ret.diffs = {key:(b, a) for (key, (a, b)) in self.diffs.items() }
        return ret
