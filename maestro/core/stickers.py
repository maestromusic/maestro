# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2012-2015 Martin Altmayer, Michael Helmling
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

class StickersDifference:
    """Efficiently stores the difference between two stickers attributes of elements."""
    def __init__(self, stickersA, stickersB):
        self.diffs = {}
        if stickersA is None:
            stickersA = {}
        if stickersB is None:
            stickersB = {}
        for key in set(stickersA.keys()) | set(stickersB.keys()):
            a = stickersA[key] if key in stickersA else None
            b = stickersB[key] if key in stickersB else None
            if a != b:
                self.diffs[key] = (a, b)
            
    def apply(self, element):
        for key, (_, b) in self.diffs.items():
            if b is None:
                del element.stickers[key]
            else:
                element.stickers[key] = b
                
    def revert(self, element):
        for key, (a, _) in self.diffs.items():
            if a is None:
                del element.stickers[key]
            else:
                element.stickers[key] = a
                
    def inverse(self):
        ret = StickersDifference(None, None)
        ret.diffs = {key:(b, a) for (key, (a, b)) in self.diffs.items() }
        return ret
