# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from omg import application
from PyQt4 import QtGui
showAction = None

def show():
    from omg import database
    db = database.get()
    text = '<h1>database statistics</h1>\n'
    result = db.query("SELECT tagname,tagtype FROM tagids")
    text += '<h2>Indexed Tags:</h2>\n<table><tr><th>name</th><th>type</th></tr>\n'
    for line in result:
        text += '<tr><td>{}</td><td>{}</td></tr>\n'.format(line[0],line[1])
    text += '</table>'
    
    text += '<h2>elements</h2><table>'
    text += '<tr><td>elements:</td><td>{}</td></tr>'.format(db.query("SELECT COUNT(*) FROM elements").getSingle())
    text += '<tr><td>files:</td><td>{}</td></tr>'.format(db.query("SELECT COUNT(*) FROM files").getSingle())
    text += '<tr><td>toplevels:</td><td>{}</td></tr>'.format(db.query("SELECT COUNT(*) FROM elements WHERE toplevel='1'").getSingle())
    text += '</table>'
    
    text += '<h2>various</h2><table>'
    text += '<tr><td>tag table size:</td><td>{}</td></tr>'.format(db.query("SELECT COUNT(*) FROM tags").getSingle())
    text += '<tr><td>contents table size:</td><td>{}</td></tr>'.format(db.query("SELECT COUNT(*) FROM contents").getSingle())
    text += '</table>'
    QtGui.QMessageBox.information(None, "statistics", text)
    
def enable():
    showAction = QtGui.QAction(application.widget.menus["extras"])
    application.widget.menus["extras"].addAction(showAction)
    showAction.setText("database information")
    
    showAction.triggered.connect(show)
   
    
def disable():
    application.widget.menus["extras"].removeAction(showAction)