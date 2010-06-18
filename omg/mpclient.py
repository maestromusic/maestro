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

# Redirect methods to the client
for name in ("play","pause","stop","next","previous","clear","seek","volume","playlist"):
    globals()[name] = getattr(client,name)

def status():
    status = client.status()
    #~ from pprint import PrettyPrinter
    #~ pp = PrettyPrinter(indent=4)
    #~ pp.pprint(status)
    status['volume'] = int(status['volume'])
    if 'time' in status:
        status['time'] = Time(status['time'])
    return status
    
        
class Time:
    """Class representing time of current song."""
    def __init__(self,string):
        """Initialize this Time-object from a string like "10:901" where the first number is the number of seconds elapsed and the second number is the length of the current piece in seconds. This format is returned by mpd.MPDClient.status()['time']."""
        self.elapsed,self.total = (int(n) for n in string.split(":",1))
    
    def getElapsed(self):
        return self.elapsed
        
    def getTotal(self):
        return self.total
    
    def getRemaining(self):
        return self.total - self.elapsed
    
    def getRatio(self):
        return self.elapsed / self.total
        
    def __eq__(self,other):
        if not isinstance(other,Time):
            return False
        return all((self.elapsed == other.elapsed,self.total == other.total))
    
    def __neq__(self,other):
        if not isinstance(other,Time):
            return True
        return any((self.elapsed != other.elapsed,self.total != other.total))