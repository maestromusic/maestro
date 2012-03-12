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
from setuptools import setup, find_packages

setup(name='OMG',
      version='0.2',
      description='OMG music GUI',
      author='Martin Altmayer, Michael Helmling',
      author_email='{altmayer,helmling}@mathematik.uni-kl.de',
      url='http://omg.mathematik.uni-kl.de',
      license='GPL3',
      
      #install_requires=['taglib>=0.0.1'],
      packages=find_packages(),
      #scripts=['bin/omg'],
      py_modules=['mpd'],
      entry_points = {
          'console_scripts' : ['omg = omg.application:run']
        }
    )

