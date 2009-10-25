# -*- coding: utf-8 -*-
# Copyright 2009 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
# realfiles.py
"""Module for working with real files, i.e. accessing tags & audio information
from various file formats."""

import subprocess
import config
import pickle
import sys
try:
    import stagger
    from stagger.id3 import * #frame definitions
except ImportError:
    pass

    
class MartinIstEinSpast:
    """Base class for special file types. All files have a path."""
    def __init__(self,path):
        self.path = path
        self.tags = {}
        self.length = None
    
    def read(self):
        """Reads all information, like tags, length, and perhaps more in the future, from the filesystem"""
        pass
        
    def save_tags(self):
        """Stores the tags that are currently present in the tags attribute in the file."""
        pass
    
    

class UglyPython26PickleFile(MartinIstEinSpast):
    """This file uses the tagmanip26.py-script so store and load data"""
    def __init__(self,path):
        MartinIstEinSpast.__init__(self,path)
    
    def read(self):
        proc = subprocess.Popen([config.get("misc","tagmanip26_cmd"),"pickle", self.path], stdout=subprocess.PIPE)
        stdout = proc.communicate()[0]
        if proc.returncode > 0:
            raise RuntimeError("Error calling printtags on file '{0}': {1}".format(self.path,stdout))
        data = pickle.loads(stdout)
        self.tags = data["tags"]
        self.length = data["length"]
    
    def save_tags(self):
        proc = subprocess.Popen([config.get("misc","tagmanip26_cmd"),"store", self.path], stdin=subprocess.PIPE)
        out = { "tags":self.tags }
        pickle.dump(out, proc.stdin,protocol=2)
        proc.stdin.flush()

class StaggerID3(MartinIstEinSpast):
    """Stagger based id3 class."""
    
    text_frames = {
            "TIT1": "grouping",                                 
            "TIT2": "title",                                    
            "TIT3": "version",                                  
            "TPE1": "artist",                                   
            "TPE2": "performer",                                
            "TPE3": "conductor",                                
            "TPE4": "arranger",                                 
            "TEXT": "lyricist",                                 
            "TCOM": "composer",                                 
            "TENC": "encodedby",                                
            "TALB": "album",                                    
            "TRCK": "tracknumber",                              
            "TPOS": "discnumber",                               
            "TSRC": "isrc",                                     
            "TCOP": "copyright",                                
            "TPUB": "organization",                             
            "TSST": "discsubtitle",                             
            "TOLY": "author",                                   
            "TMOO": "mood",                                     
            "TBPM": "bpm",                                      
            "TDRC": "date",                                     
            "TDOR": "originaldate",                             
            "TOAL": "originalalbum",                            
            "TOPE": "originalartist",                                                        
            "TSOP": "artistsort",                               
            "TSOA": "albumsort",                                
            "TSOT": "artistsort",                               
            "TMED": "media",                                    
            "TCMP": "compilation",
            "TCON": "genre",
            "TOWN": "owner", # file owner/licensee
            "TLAN": "language",  # "language" should not make to TLAN. TLAN requires
            # an ISO language code, and QL tags are freeform.   
            "TLEN": "length", #milliseconds in string format
            }
    def __init__(self,path):
        MartinIstEinSpast.__init__(self,path)
        self._stag = None
    
    @staticmethod
    def _decode(encodingNr, string):
        if encodingNr==0: # do we really need this?
            return string.encode("iso-8859-1").decode("utf-8")
        else:
            return string
        
    def read(self):
        self._stag = stagger.read_tag(self.path)
        for key in self._stag:
            if key in StaggerID3.text_frames:
                frame = self._stag[key]
                tag = [StaggerID3._decode(frame.encoding,t) for t in frame.text]
                self.tags[StaggerID3.text_frames[key]] = tag
            elif key=="TXXX":
                # the TXXX frame is a list of description,value pairs
                for part in self._stag["TXXX"]:
                    description = StaggerID3._decode(part.encoding, part.description)
                    if description.startswith("QuodLibet::"):
                        description = description[11:] # hass auf quodlibet ...
                    value = StaggerID3._decode(part.encoding, part.value)
                    self.tags[description] = [ value ]
            elif key=="COMM":
                # comment tag
                for part in self._stag["COMM"]:
                    value = StaggerID3._decode(part.encoding, part.text)
                    if part.desc=="":
                        self.tags["comment"] = [ value ]
                    else:
                        description = StaggerID3._decode(part.encoding, part.desc)
                        self.tags[description] = [ value ]
            else:
                print("Skipping unsupported tag {0} in id3 file '{1}'".format(key,self.path))
                
        

def File(path):
    """Factory method, will return an appropriate MartinIstEinSpast instance."""
    if path.rsplit(".",1)[1].lower() == "mp3" and 'stagger' in sys.modules:
        return StaggerID3(path)
    else:
        return UglyPython26PickleFile(path)
