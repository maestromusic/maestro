# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2013 Martin Altmayer, Michael Helmling
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

"""Run all unittests."""

import unittest

def load_tests(loader, standard_tests, pattern):
    # See http://docs.python.org/py3k/library/unittest.html#load-tests-protocol
    # Remember that OMG uses its own test loader (see testloader.py)
    suite = unittest.TestSuite()

    from . import sql
    suite.addTests(loader.loadTestsFromModule(sql))
    
    from . import tagflagtypes
    suite.addTests(loader.loadTestsFromModule(tagflagtypes))
    
    from . import levels
    suite.addTests(loader.loadTestsFromModule(levels))
    
    from . import realfiles
    suite.addTests(loader.loadTestsFromModule(realfiles))
    
    from . import playlistmodel
    suite.addTests(loader.loadTestsFromModule(playlistmodel))
    
    return suite

if __name__ == "__main__":
    print("To run all tests use: python setup.py test")
    