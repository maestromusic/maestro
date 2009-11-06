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
        raise NotImplementedError
        
    def save_tags(self):
        """Stores the tags that are currently present in the tags attribute in the file."""
        raise NotImplementedError
    
    

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
            "TT1" : "grouping",
            "TIT2": "title", 
            "TT2" : "title",                                   
            "TIT3": "version", 
            "TT3" : "version",                                 
            "TPE1": "artist",    
            "TP1" : "artist",                               
            "TPE2": "performer",                                
            "TPE3": "conductor",                                
            "TPE4": "arranger",                                 
            "TEXT": "lyricist",                                 
            "TCOM": "composer",                                 
            "TENC": "encodedby",                                
            "TALB": "album", 
            "TAL" : "album",                                   
            "TRCK": "tracknumber",
            "TRK": "tracknumber",                           
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
            "TYE": "date",
            "TDOR": "originaldate",                             
            "TOAL": "originalalbum",                            
            "TOPE": "originalartist",                                                        
            "TSOP": "artistsort",                               
            "TSOA": "albumsort",                                
            "TSOT": "artistsort",                               
            "TMED": "media",                                    
            "TCMP": "compilation",
            "TCON": "genre",
            "TCO" : "genre",
            "TOWN": "owner", # file owner/licensee
            "TLAN": "language",  # "language" should not make to TLAN. TLAN requires
            # an ISO language code, and QL tags are freeform.   
            "TLEN": "length", #milliseconds in string format
            "USLT": "lyrics", # not a text frame, but should also have a text attribute
            "TSSE": "encoder",
            "TFLT": "filetype",
            }
    ignored_frames = [
        "XDOR", # old experimental date format, not read correctly by stagger
        "XSOP", # replaced by TSOP, not read by stagger
        "PIC", "APIC", #pictures not handled yet
        "NCON", #nonstandard tag by musicmatch :(
        "TDAT", #month/day date in id3v2.3
        "PRIV", #private stuff
        "UFID", #unique file identifier
        "MCDI", #binary zeugs
        "PCNT", # playcount shouldn't be inside the file!?
        "GEOB", #general object
        
        ] #TODO: don't simpy ignore those

    def __init__(self,path):
        MartinIstEinSpast.__init__(self,path)
        self._stag = None
          
    def _decode_id3v1(self):
        
        for key in self._stag.__dict__:
            if key=="_genre":
                self.tags["genre"] = [ stagger.id3.genres[self._stag.__dict__[key]] ]
            else:
                self.tags[key] = [ self._stag.__dict__[key] ]
        
    def read(self):
        self.ignored_tags = set()
        try:
            self._stag = stagger.read_tag(self.path)
        except stagger.errors.NoTagError as e:
            # try to find an id3v1 tag (stagger.read_tag() only finds id3v1 atm
            try:
                self._stag = stagger.id3v1.Tag1.read(self.path)
                self._decode_id3v1
                return
            except stagger.errors.NoTagError as e2:
                raise NoTagError(str(e)) # we use our own errors, ofc
            
        for key in self._stag:
            if key in StaggerID3.ignored_frames:
                self.ignored_tags.add(key)
                continue
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
                    description = part.description
                    if description.startswith("QuodLibet::"):
                        description = description[11:] # hass auf quodlibet ...
                    self.tags[description] = [ part.value ]
            elif key in ("COMM", "COM"):
                # comment tag
                for part in self._stag[key]:
                    value = part.text
                    if part.desc=="":
                        self.tags["comment"] = [ value ]
                    else:
                        self.tags[part.desc] = [ value ]
            elif key=="WXXX":
                # user defined url
                for part in self._stag["WXXX"]:
                    value = part.url
                    if part.description=="":
                        self.tags["url"] = [ value ]
                    else:
                        self.tags[part.description] = [ value ]
            elif isinstance(self._stag[key][0], stagger.frames.URLFrame):
                if "url" not in self.tags:
                    self.tags["url"] = []
                for part in self._stag[key]:
                    self.tags["url"].append(part.url)
                    
            else:
                print("Skipping unsupported tag {0} in id3 file '{1}'".format(key,self.path))
                self.ignored_tags.add(key)
                
        

def File(path):
    """Factory method, will return an appropriate MartinIstEinSpast instance."""
    if path.rsplit(".",1)[1].lower() == "mp3" and 'stagger' in sys.modules:
        return StaggerID3(path)
    else:
        return UglyPython26PickleFile(path)

if __name__=="__main__":
    """Small testing procedure that searches for MP3 files and tries to read all their tags."""
    import logging
    logger = logging.getLogger("spast")
    logger.setLevel(logging.WARNING)
    path = sys.argv[1]
    mp3count = 0
    notagcount = 0
    bahlistcount = 0
    ignored = {}
    types = {}
    for dp,dn,fn in os.walk(path):
        for f in fn:
            filename = os.path.join(dp,f)
            try:
                ending = filename.rsplit(".",1)[1].lower()
                if ending=="mp3":
                    testfile = File(filename)
                    mp3count += 1
                    logger.debug("Reading file '{0}'".format(filename))
                    try:
                        testfile.read()
                        if hasattr(testfile,"bahlist"):
                            bahlistcount +=1
                        for ign in testfile.ignored_tags:
                            if ign not in ignored:
                                ignored[ign] = []
                            ignored[ign].append(filename)
                        classname = type(testfile._stag).__name__
                        if classname not in types:
                            types[classname] = 0
                        types[classname] += 1
                    except NoTagError:
                        logger.info("    File has no tag at all. [enter] to continue")
                        notagcount += 1
            except IndexError:
                pass
    print("Statistics I have collected:")
    print("You have {0} mp3 files, of which:".format(mp3count))
    print("   * {0} have no tag at all".format(notagcount))
    for t in types:
        print("   * {0} have tag of type {1}".format(types[t], t))
    print("   * {0} have wrong multiple tags".format(bahlistcount))
    print("Ignored tags I have found:")
    for frame in ignored:
        print("  {0} ({1})".format(frame,len(ignored[frame])))
