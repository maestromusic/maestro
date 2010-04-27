#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
import mpd
from omg import database, config

db = database.get()
client = mpd.MPDClient()
client.connect(config.get("mpd","host"),config.get("mpd","port"))


    
def addContainer(id):
    file = db.query("SELECT path FROM files WHERE container_id = {0}".format(id)).getSingle()
    client.add(file)
    
def addContainers(list):
    for id in list:
        addContainer(id)
        
# Redirect methods to the client
for name in ("play","pause","stop","next","previous","clear"):
    globals()[name] = getattr(client,name)