#!/usr/bin/python3
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

import sys

if sys.version_info.major <= 2:
    print("OMG runs with Python 3.x only. "
          "Please re-run setup.py with a Python3 interpreter.")
    sys.exit(1)

import distribute_setup

distribute_setup.use_setuptools()

import glob, os.path, subprocess
from os.path import dirname, exists, join, getmtime

from setuptools import setup, find_packages
from setuptools.command import sdist, install, develop, test

if exists(join(dirname(__file__), '.git')):
    def updateTranslations():
        """Create *.qm files from *.ts in i18n folder if necessary."""
        tsFiles = glob.glob("i18n/*.ts")
        proFile = "i18n/omg.pro"
        for tsFile in tsFiles:
            qmFile = tsFile[:-2] + "qm"
            if not os.path.exists(qmFile) or getmtime(tsFile) > getmtime(qmFile):
                print("Updating translation file: {}".format(qmFile))
                try:
                    subprocess.check_call(["lrelease", proFile])
                except Exception as e:
                    print(e)
                    try:
                        subprocess.check_call(["lrelease-qt4", proFile])
                    except Exception as e:
                        print(e)
                        print("Warning: Could not update translations")
                        return
        
    
    def updateResources():
        """Update resource files with pyrcc4 if necessary."""
        resources = [ (["images/images.qrc"], "omg/resources.py"),
                      (["i18n/translations.qrc"] + glob.glob("i18n/*.qm"), "omg/translations.py") ]
        pluginBaseDir = os.path.join("omg", "plugins")
        for subdir in os.listdir(pluginBaseDir):
            pluginDir = os.path.join(pluginBaseDir, subdir)
            if os.path.exists(os.path.join(pluginDir, "resources.qrc")):
                resources.append( ([os.path.join(pluginDir, "resources.qrc")],
                                   os.path.join(pluginDir, "resources.py")) )
        for sources, py in resources:
            for source in sources:
                if not os.path.exists(py) or getmtime(source) > getmtime(py):
                    print("Updating resource file: {}".format(py))
                    subprocess.check_call(["pyrcc4", "-py3", "-o", py, sources[0]])
                    break
    
    # Now we monkey-path the relevant commands to update i18n & resources on demand
    sdist_run = sdist.sdist.run
    def wrapped_sdist_run(self):
        updateTranslations()
        updateResources()
        sdist_run(self)
    sdist.sdist.run = wrapped_sdist_run
    
    install_run = install.install.run
    def wrapped_install_run(self):
        updateTranslations()
        updateResources()
        install_run(self) 
    install.install.run = wrapped_install_run
    
    develop_run = develop.develop.run
    def wrapped_develop_run(self):
        updateTranslations()
        updateResources()
        develop_run(self)
    develop.develop.run = wrapped_develop_run
    
    test_run = test.test.run
    def wrapped_test_run(self):
        updateTranslations()
        updateResources()
        test_run(self)
    test.test.run = wrapped_test_run

setup(name='omg',
      version='0.3',
      description='OMG music GUI',
      author='Martin Altmayer, Michael Helmling',
      author_email='{altmayer,helmling}@mathematik.uni-kl.de',
      url='http://omg.mathematik.uni-kl.de',
      license='GPL3',
      packages=find_packages(),
      include_package_data=True,
      #py_modules=['distribute_setup'],
      entry_points = {
          'gui_scripts' : ['omg = omg.application:run',
                           'omgsetup = omg.install:run',
                           'omgdbanalyzer = omg.plugins.dbanalyzer.plugin:run'], 
          },
      test_loader = "test.testloader:TestLoader",
      test_suite = "test.all"
    )

