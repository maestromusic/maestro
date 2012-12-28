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

import sys

if sys.version_info.major <= 2:
  print("OMG runs with Python 3.x only. "
        "Please re-run setup.py with a Python3 interpreter.")
  sys.exit(1)

import distribute_setup
distribute_setup.use_setuptools()
from setuptools import setup, find_packages
import setuptools.command.sdist
import setuptools.command.install
import setuptools.command.develop
import setuptools.command.test


def updateResources():
    import os, subprocess
    resources = [ ("images/images.qrc", "omg/resources.py"),
                  ("i18n/translations.qrc", "omg/translations.py") ]
    pluginBaseDir = os.path.join("omg", "plugins")
    for subdir in os.listdir(pluginBaseDir):
        pluginDir = os.path.join(pluginBaseDir, subdir)
        if os.path.exists(os.path.join(pluginDir, "resources.qrc")):
            resources.append( (os.path.join(pluginDir, "resources.qrc"),
                               os.path.join(pluginDir, "resources.py")) )
    for qrc, py in resources:
        if not os.path.exists(py) or os.path.getmtime(qrc) > os.path.getmtime(py):
            print("Updating resource file: {}".format(py))
            subprocess.check_call(["pyrcc4", "-py3", "-o", py, qrc])

sdist_run = setuptools.command.sdist.sdist.run
def wrapped_sdist_run(self):
    updateResources()
    sdist_run(self)
setuptools.command.sdist.sdist.run = wrapped_sdist_run

install_run = setuptools.command.install.install.run
def wrapped_install_run(self):
    updateResources()
    install_run(self) 
setuptools.command.install.install.run = wrapped_install_run

develop_run = setuptools.command.develop.develop.run
def wrapped_develop_run(self):
    updateResources()
    develop_run(self) 
setuptools.command.develop.develop.run = wrapped_develop_run

test_run = setuptools.command.test.test.run
def wrapped_test_run(self):
    updateResources()
    test_run(self)
setuptools.command.test.test.run = wrapped_test_run

setup(name='omg',
      version='0.3-currentgit',
      description='OMG music GUI',
      author='Martin Altmayer, Michael Helmling',
      author_email='{altmayer,helmling}@mathematik.uni-kl.de',
      url='http://omg.mathematik.uni-kl.de',
      license='GPL3',
      packages=find_packages(),
      include_package_data = True,
      py_modules=['mpd', 'distribute_setup'],
      entry_points = {
          'gui_scripts' : ['omg = omg.application:run',
                           'omgsetup = omg.install:run',
                           'omgdbanalyzer = omg.plugins.dbanalyzer.plugin:run'], 
          },
      test_loader = "test.testloader:TestLoader",
      test_suite = "test.all"
    )

