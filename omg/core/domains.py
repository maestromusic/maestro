# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2014 Martin Altmayer, Michael Helmling
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

import os.path

from .. import database as db, logging

domains = []
sources = []


class Domain:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        
class Source:
    def __init__(self, id, name, path, domain):
        self.id = id
        self.name = name
        self.path = os.path.normpath(path)
        self.domain = domain
        
        
def init():
    result = db.query("SELECT id, name FROM {p}domains ORDER BY name")
    for row in result:
        domains.append(Domain(*row))
    if len(domains) == 0:
        logging.error(__name__, "No domain defined.")
        raise RuntimeError()
    
    result = db.query("SELECT id, name, path, domain FROM {p}sources ORDER BY name")
    for row in result:
        sources.append(Source(*row[:3], domain=domainById(row[3])))
    if len(sources) == 0:
        logging.error(__name__, "No source defined.")
        raise RuntimeError()
    

def domainById(id):
    for domain in domains:
        if domain.id == id:
            return domain
    else: return None
    

def sourceById(id):
    for source in sources:
        if source.id == id:
            return source
    else: return None
        
        
def getSource(path):
    if not isinstance(path, str): # Should be a BackendURL
        path = path.path
    path = os.path.normpath(path)
    for source in sources:
        if path.startswith(source.path):
            return source
    else: return None
