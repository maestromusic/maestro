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
import os
try: # we try to favor native Pyk3 stagger support over the ugly26 shit
    import stagger
    from stagger.id3 import * #frame definitions
except ImportError:
    pass

class NoTagError(Exception):
    """This Exception occurs if you try to read tags from a file that has no tags."""
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
            "TYER": "date", #replaced by TDRC in id3v2.4
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
            return string #.encode("iso-8859-1").decode("utf-8")
        else:
            return string
        
    def _decode_id3v1(self):
        
        for key in self._stag.__dict__:
            if key=="_genre":
                self.tags["genre"] = [ stagger.id3.genres[self._stag.__dict__[key]] ]
            else:
                self.tags[key] = [ self._stag.__dict__[key] ]
        
    def read(self):
        self._bad_id3v1 = False
        try:
            self._stag = stagger.read_tag(self.path)
        except stagger.errors.NoTagError as e:
            # try to find an id3v1 tag (stagger.read_tag() only finds id3v1 atm
            try:
                self._stag = stagger.id3v1.Tag1.read(self.path)
                self._decode_id3v1
                self._bad_id3v1 = True
                return
            except stagger.errors.NoTagError as e2:
                raise NoTagError(str(e)) # we use our own errors, ofc
            
        for key in self._stag:
            if key in StaggerID3.text_frames:
                frame = self._stag[key]
                if not isinstance(frame, stagger.frames.ErrorFrame):
                    if isinstance(frame, list):
                        self.bahlist = True
                        textkey = StaggerID3.text_frames[key]
                        self.tags[textkey] = []
                        for subframe in frame:
                            self.tags[textkey].append(subframe.text)
                    else:
                        # this should be the normal case
                        self.tags[StaggerID3.text_frames[key]] = frame.text
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

if __name__=="__main__":
    """Small testing procedure that searches for MP3 files and tries to read all their tags."""
    path = sys.argv[1]
    id3v1count = 0
    badid3v1count = 0
    mp3count = 0
    notagcount = 0
    bahlistcount = 0
    for dp,dn,fn in os.walk(path):
        for f in fn:
            filename = os.path.join(dp,f)
            try:
                ending = filename.rsplit(".",1)[1].lower()
                if ending=="mp3":
                    testfile = File(filename)
                    mp3count += 1
                    print("Reading file '{0}'".format(filename))
                    try:
                        testfile.read()
                        if hasattr(testfile,"bahlist"):
                            bahlistcount +=1
                        if isinstance(testfile._stag, stagger.id3v1.Tag1):
                            print("    file has id3v1 Tag")
                            id3v1count += 1
                            if testfile._bad_id3v1:
                                badid3v1count += 1
                        else:
                            print("    OK.")
                    except NoTagError:
                        print("    File has no tag at all. [enter] to continue")
                        notagcount += 1
            except IndexError:
                pass
    print("Statistics I have collected:")
    print("You have {0} mp3 files, of which:".format(mp3count))
    print("   * {0} have no tag at all".format(notagcount))
    print("   * {0} have an id3v1 tag".format(id3v1count))
    print("   * {0} have a bad id3v1 tag".format(id3v1count))
    print("   * {0} have wrong multiple tags".format(bahlistcount))
