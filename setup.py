#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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

if sys.version_info <= (3,3):
    print("Maestro runs with Python 3.3+ only.")
    sys.exit(1)

import glob, os.path, subprocess
from os.path import dirname, exists, join, getmtime

from setuptools import setup, find_packages
from setuptools.command import sdist, install, develop, test

CLASSIFIERS = [
    'Development Status :: 4 - Beta',
    'Intended Audience :: End Users/Desktop',
    'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
    'Natural Language :: English',
    'Natural Language :: German',
    'Operating System :: POSIX :: Linux',
    'Environment :: X11 Applications :: Qt',
    'Programming Language :: Python :: 3',
    'Topic :: Multimedia :: Sound/Audio :: Players'
]

if exists(join(dirname(__file__), '.git')):
    def updateTranslations():
        """Create *.qm files from *.ts in i18n folder if necessary."""
        tsFiles = glob.glob("i18n/*.ts")
        proFile = "i18n/maestro.pro"
        for tsFile in tsFiles:
            qmFile = tsFile[:-2] + "qm"
            if not os.path.exists(qmFile) or getmtime(tsFile) > getmtime(qmFile):
                print("Updating translation file: {}".format(qmFile))
                try:
                    subprocess.check_call(["lrelease", proFile])
                except Exception as e:
                    try:
                        subprocess.check_call(["lrelease-qt4", proFile])
                    except Exception as e:
                        print(e)
                        print("Warning: Could not update translations")
                        return
        
    
    def updateResources():
        """Update resource files with pyrcc4 if necessary."""
        resources = [ (["images/images.qrc"], "maestro/resources.py"),
                      (["i18n/translations.qrc"] + glob.glob("i18n/*.qm"), "maestro/translations.py") ]
        pluginBaseDir = os.path.join("maestro", "plugins")
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

setup(name='maestro',
      version='0.4.0',
      description='Maestro music manager and player',
      author='Martin Altmayer, Michael Helmling',
      author_email='martin.altmayer@web.de, michaelhelmling@posteo.de',
      url='https://github.com/maestromusic/maestro',
      license='GPL3',
      packages=find_packages(),
      include_package_data=True,
      install_requires=["pytaglib>=0.3.0", "pyparsing", "sqlalchemy"],
      extras_require={ 'mpd': ["python-mpd2>=0.5.3"] },
      entry_points={
          'gui_scripts': ['maestro = maestro.application:run',
                          'maestro-setup = maestro.install:run',
                          'maestro-dbanalyzer = maestro.plugins.dbanalyzer.plugin:run'], 
          },
      test_loader="test.testloader:TestLoader",
      test_suite="test.all"
    )

