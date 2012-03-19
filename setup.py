#!/usr/bin/python3
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
import distribute_setup
distribute_setup.use_setuptools()
from setuptools import setup, find_packages
from setuptools.command.sdist import sdist
original_run = sdist.run
def sdist_run(self):
    import subprocess
    subprocess.check_call(["/bin/sh", "update_resources.sh"])
    original_run(self)
    
sdist.run = sdist_run

setup(name='omg',
      version='0.2',
      description='OMG music GUI',
      author='Martin Altmayer, Michael Helmling',
      author_email='{altmayer,helmling}@mathematik.uni-kl.de',
      url='http://omg.mathematik.uni-kl.de',
      license='GPL3',
      packages=find_packages(),
      include_package_data = True,
      py_modules=['mpd', 'distribute_setup'],
      entry_points = {
          'gui_scripts' : ['omg = omg.application:run'], 
          }
    )

