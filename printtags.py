#!/usr/bin/env python2.6
# -*- coding: utf-8 -*-

import sys
import subprocess
import mutagen

class UnsupportedFileExtension(Exception):
    pass

ID3_MAPPING = {
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
            "WOAR": "website",                                  
            "TSOP": "artistsort",                               
            "TSOA": "albumsort",                                
            "TSOT": "artistsort",                               
            "TMED": "media",                                    
            "TCMP": "compilation",
            "TCON": "genre",
            "TXXX": "decsription" #this is getting messy if you wanna do it 'right'
            # "language" should not make to TLAN. TLAN requires 
            # an ISO language code, and QL tags are freeform.   
            }
ID3_IGNORE = [
        "TLEN", # no need to get file length from a tag ...
        "APIC",  # pictures not supported
        "PRIV",
        "MCDI", # binary crap
        ]

def gettags(filename):
    """Obtains all tags from a filename and returns them as dictionary with tagnames as keys and values
    as list."""
    extension = filename.rsplit(".",1)[1].lower()
    if not extension in ["mp3","flac","ogg"]:
        print(filename)
        raise UnsupportedFileExtension
    f = mutagen.File(filename)
    if extension=="mp3":
        tags = f.tags
        ntags = {}
        for tag in tags:
            frameid = tags[tag].FrameID
            if tag in ID3_IGNORE:
                continue
            elif tag.startswith("APIC"):
                continue #pictures
            elif tag.startswith("PRIV"):
                continue #private tags are bäh
            try:
                nice_tag = ID3_MAPPING[frameid]
            except:
                print("Unsupported ID3 tag: {0} ({1})".format(frameid,tag))
                nice_tag = frameid
            if not nice_tag in ntags:
                ntags[nice_tag] = []
            for value in tags[tag].text:
                if frameid=="TXXX":
                    try:
                        value = tags[tag].desc + "=" + value
                    except AttributeError:
                        pass
                else:
                    ntags[nice_tag].append(value)
        tags = ntags
    else:
        tags = {}
        for tag,value in f.tags:
            if not tag.lower() in tags:
                tags[tag.lower()] = []
            tags[tag.lower()].append(value)
    return tags

if __name__=="__main__":
    filename = sys.argv[1]
    tags = gettags(filename)
    for tag in tags:
        for value in tags[tag]:
            print(u"{0}={1}".format(tag,value).encode("utf-8"))
    
    
