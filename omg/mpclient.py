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

class CommandError(Exception):
    """Error that is thrown when a command send to MPD did not succeed."""
    def __init__(self,message):
        """Initialize the error with the given error message."""
        self.message = message

db = database.get()
client = mpd.MPDClient()
client.connect(config.get("mpd","host"),config.get("mpd","port"))

# Redirect methods to the client
for name in ("play","pause","stop","next","previous","clear","seek","setvol","volume","playlist"):
    globals()[name] = getattr(client,name)

def status():
    """Return MPD's status as a dictionary. For the fields confer e.g. http://search.cpan.org/~jquelin/Audio-MPD-Common-1.100430/lib/Audio/MPD/Common/Status.pm. But note that this method changes some fields:
    - volume will be converted to int
    - time will be returned as a Time-object, which contains information of the elapsed an the total time.
    """
    try:
        status = client.status()
    except mpd.CommandError as e:
        raise CommandError(e.message)
    #~ from pprint import PrettyPrinter
    #~ pp = PrettyPrinter(indent=4)
    #~ pp.pprint(status)
    status['volume'] = int(status['volume'])
    if 'time' in status:
        status['time'] = Time(status['time'])
    return status

def insert(offset,file):
    """Insert the given file (which may be a path or something with a 'getPath'-method and insert it into MPD's playlist. Return True when the file was inserted and false else (which happens usually because the file is not in MPD's own database."""
    if isinstance(file,str):
        path = file
    elif hasattr(file,'getPath'):
        path = file.getPath()
    else: raise ValueError("File must be either a path or something with a getPath-method.")
    
    try:
        client.add(path)
        client.move(int(client.status()['playlistlength'])-1,offset)
        return True
    except mpd.CommandError:
        return False
            
def delete(start,end=None):
    """Remove the files with offsets between <start> and <end> (without <end>!) from MPD's playlist. Raise a CommandError when this fails."""
    if end is None:
        end = start + 1
    for i in range(start,end):
        try:
            client.delete(start) # Always delete start since the indices will decrease
        except mpd.CommandError as e:
            raise CommandError(e.message)


class Time:
    """Class representing time of current song."""
    def __init__(self,string):
        """Initialize this Time-object from a string like "10:901" where the first number is the number of seconds elapsed and the second number is the length of the current piece in seconds. This format is returned by mpd.MPDClient().status()['time']."""
        self.elapsed,self.total = (int(n) for n in string.split(":",1))
    
    def getElapsed(self):
        """Return the elapsed time in seconds."""
        return self.elapsed
        
    def getTotal(self):
        """Return the total time in seconds."""
        return self.total
    
    def getRemaining(self):
        """Return the remaining time in seconds."""
        return self.total - self.elapsed
    
    def getRatio(self):
        """Return the ratio of elapsed time to total time."""
        return self.elapsed / self.total
        
    def __eq__(self,other):
        if not isinstance(other,Time):
            return False
        return all((self.elapsed == other.elapsed,self.total == other.total))
    
    def __neq__(self,other):
        if not isinstance(other,Time):
            return True
        return any((self.elapsed != other.elapsed,self.total != other.total))