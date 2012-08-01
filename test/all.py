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

"""Run all unittests except sql.py which requires a different database connection."""

if __name__ == "__main__":
    import sys, unittest, os.path
    sys.path.insert(0,os.path.normpath(os.path.join(os.getcwd(),os.path.dirname(__file__),'../')))
    
    from omg import application
    application.init(exitPoint='noplugins')
    
    suite = unittest.TestSuite()
    
    import playlistmodel
    suite.addTest(playlistmodel.suite)
    
    import realfiles
    suite.addTest(realfiles.suite)
    
    unittest.TextTestRunner(verbosity=2).run(suite)
    