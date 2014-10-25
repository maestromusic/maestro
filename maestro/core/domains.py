# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
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

from PyQt4 import QtCore, QtGui
translate = QtCore.QCoreApplication.translate

from .. import application, database as db, logging, constants, stack
from ..constants import ADDED, DELETED, CHANGED
from ..application import ChangeEvent

domains = []
    
# Maximum length of encoded domain names.
MAX_NAME_LENGTH = 63

def isValidName(name):
    return name == name.strip() and 0 < len(name.encode()) <= MAX_NAME_LENGTH 


def exists(name):
    return any(domain.name == name for domain in domains)
    
    
def domainById(id):
    for domain in domains:
        if domain.id == id:
            return domain


def domainByName(name):
    for domain in domains:
        if domain.name == name:
            return domain


def init():
    if db.prefix+'domains' not in db.listTables():
        logging.error(__name__, "domains-table is missing")
        raise RuntimeError()
    
    result = db.query("SELECT id, name FROM {p}domains ORDER BY name")
    for row in result:
        domains.append(Domain(*row))
    if len(domains) == 0:
        logging.error(__name__, "No domain defined.")
        raise RuntimeError()
    
    
class Domain:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        
    def __repr__(self):
        return "<Domain {}>".format(self.name)
    
    
def addDomain(name):
    """Add a new domain with the given name to the database. Return the new domain."""
    if exists(name):
        raise ValueError("There is already a domain with name '{}'.".format(name))
    if not isValidName(name):
        raise ValueError("'{}' is not a valid domain name.".format(name))
    domain = Domain(None, name)
    stack.push(translate("Domains", "Add domain"),
               stack.Call(_addDomain, domain),
               stack.Call(_deleteDomain, domain))
    return domain
    
    
def _addDomain(domain):
    """Add a domain to database and some internal lists and emit a DomainChanged-event. If *domain*
    doesn't have an id, choose an unused one.
    """
    if domain.id is None:
        domain.id = db.query("INSERT INTO {p}domains (name) VALUES (?)", domain.name).insertId()
    else: db.query("INSERT INTO {p}domains (id, name) VALUES (?,?)", domain.id, domain.name)
    logging.info(__name__, "Added new domain '{}'".format(domain.name))
    
    domains.append(domain)
    application.dispatcher.emit(DomainChangeEvent(ADDED, domain))


def deleteDomain(domain):
    """Delete a domain from all elements and the database."""
    stack.push(translate("Domains", "Delete domain"),
               stack.Call(_deleteDomain, domain),
               stack.Call(_addDomain, domain))
    
    
def _deleteDomain(domain):
    """Like deleteDomain but not undoable."""
    assert db.query("SELECT COUNT(*) FROM {p}elements WHERE domain=?", domain.id).getSingle() == 0
    if domains == [domain]:
        raise RuntimeError("Cannot delete last domain.")
    logging.info(__name__, "Deleting domain '{}'.".format(domain))
    db.query("DELETE FROM {p}domains WHERE id = ?", domain.id)
    domains.remove(domain)
    application.dispatcher.emit(DomainChangeEvent(DELETED, domain))


def changeDomain(domain, **data):
    """Change a domain. The attributes that should be changed must be specified by keyword arguments.
    Currently only 'name' is supported.
    """
    oldData = {'name': domain.name}
    stack.push(translate("Domains ", "Change domain"),
               stack.Call(_changeDomain, domain, **data),
               stack.Call(_changeDomain, domain, **oldData))
    
    
def _changeDomain(domain, **data):
    """Like changeDomain but not undoable."""
    # Below we will build a query like UPDATE domains SET ... using the list of assignments (e.g. (name=?).
    # The parameters will be sent with the query to replace the questionmarks.
    assignments = []
    params = []
    
    if 'name' in data:
        name = data['name']
        if name != domain.name:
            if exists(name):
                raise ValueError("There is already a domain named '{}'.".format(name))
            logging.info(__name__, "Changing domain name '{}' to '{}'.".format(domain.name, name))
            assignments.append('name = ?')
            params.append(name)
            domain.name = name
    
    if len(assignments) > 0:
        params.append(domain.id) # for the where clause
        db.query("UPDATE {p}domains SET "+','.join(assignments)+" WHERE id = ?", *params)
        application.dispatcher.emit(DomainChangeEvent(CHANGED, domain))


class DomainChangeEvent(ChangeEvent):
    """DomainChangeEvents are used when a domain is added, changed or deleted."""
    def __init__(self, action, domain):
        assert action in constants.CHANGE_TYPES
        self.action = action
        self.domain = domain
    