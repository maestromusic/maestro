#!/usr/bin/env python2.6
# -*- coding: utf-8 -*-

import mutagen
import sys
import os

class UnsupportedFileExtension(Exception):
    pass
class UnknownTagException(Exception):
    def __init__(self,tag):
        self.tag = tag
    
    def __str__(self):
        return repr(self.tag)
    
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
            "TSOP": "artistsort",                               
            "TSOA": "albumsort",                                
            "TSOT": "artistsort",                               
            "TMED": "media",                                    
            "TCMP": "compilation",
            "TCON": "genre",
            "TXXX": "description", #this is getting messy if you wanna do it 'right'
            "COMM": "description", #omgwtf
            "USLT": "lyrics",
            "TOWN": "owner", # file owner/licensee
  
            # "language" should not make to TLAN. TLAN requires 
            # an ISO language code, and QL tags are freeform.   
            }
ID3_REVERSE = dict(((v, k) for k, v in ID3_MAPPING.iteritems()))
ID3_IGNORE = [
        "TLEN", # no need to get file length from a tag ...
        "APIC",  # pictures not supported
        "PRIV",
        "MCDI", # binary crap
        "TLAN", #language
        "PCNT", #play count WTF
        "TSSE", # encoder settings freakscheiße die keinen interessiert
        "POPM", #popularity rating könnte man implementieren als popularity, aber hässlich da kein text-tag
        "TFLT", # file type, erkennt man auch so an der datei -.-
        "WXXX",
        "GEOB", #general object 
        "TDEN", #encoding time
        "TDTG",
        "LINK", #freakscheiß den eh keiner richtig benutzt
        "UFID", # unique file identifier; don't need this since we use own hashes
        "USER",
        "WCOP",
        "WOAS",
        "WOAF",
        "WOAR",
        "WORS",
        "WPUB",
        "WCOM",
        "TOFN",
        "WPAY",
        "TIPL", #involved people list, would be nice but messy to implement
        ]

APE_MAPPING = {
    "Track":"tracknumber",
    "Year":"date"
    }
MP4_MAPPING = {
    "\xa9nam": "title",
    "\xa9alb": "album",
    "\xa9ART": "artist",
    "aART": "albumartist",
    "\xa9wrt": "composer",
    "\xa9day": "date",
    "\xa9cmt": "comment",
    "\xa9grp": "grouping",
    "\xa9gen": "genre",
    "trkn" : "tracknumber",
    "tmpo": "bpm",
    "disk": "dicsnumber",
    "\xa9too": "encodedby",
    "\xa9url": "url",
    "----:com.apple.iTunes:MusicBrainz Artist Id":
        "musicbrainz_artistid",
    "----:com.apple.iTunes:MusicBrainz Track Id": "musicbrainz_trackid",
    "----:com.apple.iTunes:MusicBrainz Album Id": "musicbrainz_albumid",
    "----:com.apple.iTunes:MusicBrainz Album Artist Id":
        "musicbrainz_albumartistid",
    "----:com.apple.iTunes:MusicIP PUID": "musicip_puid",
    "----:com.apple.iTunes:MusicBrainz Album Status":
        "musicbrainz_albumstatus",
    "----:com.apple.iTunes:MusicBrainz Album Type":
        "musicbrainz_albumtype",
    "----:com.apple.iTunes:MusicBrainz Album Release Country":
        "releasecountry",
    "cpil":"compilation",
    }
MP4_IGNORE = [
    "covr",
    "\xa9cpy",
    "\xa9enc",
    "----:com.apple.iTunes:iTunes_CDDB_IDs",
    "----:com.apple.iTunes:iTunes_CDDB_1",
    '----:com.apple.iTunes:Encoding Params',
    "cpil",
    '----:com.apple.iTunes:iTunNORM',
    "pgap",
    ]
    
class TagFile:
    def __init__(self,path):
        self.tags = {}
        self.length = None
        self.ignored = []
        self.mutagen_file = mutagen.File(path)
        self.length = self.mutagen_file.info.length
        self.__getitem__=self.tags.__getitem__
    
    def delete_ignored(self):
        """Deletes all tags from the file that are in the above ignore lists."""
        
        for tag in self.ignored:
            del self.mutagen_file[tag]
        self.mutagen_file.save()
        
    def save_tags(self, tags=None):
        """Save tags into the file."""
        raise NotImplementedError

class MP3File(TagFile):
    def __init__(self,path):
        TagFile.__init__(self,path)
        f = self.mutagen_file
        tags = f.tags
        if tags == None:
            return
        for tag in tags:
            frameid = tags[tag].FrameID
            if frameid=="APIC":
                self.has_pic=True
                continue
            if tag in ID3_IGNORE:
                self.ignored.append(tag)
                continue
            elif frameid in ID3_IGNORE:
                self.ignored.append(tag)
                continue
            try:
                nice_tag = ID3_MAPPING[frameid]
            except KeyError:
                try:
                    nice_tag = ID3_MAPPING[tag]
                except KeyError:
                    print("Unsupported ID3 tag: {0} ({1})".format(frameid,tag))
                    raise UnknownTagException(frameid)
            if not nice_tag in self.tags:
                self.tags[nice_tag] = []
            for value in tags[tag].text:
                if frameid=="TXXX":
                    try:
                        value = tags[tag].desc + "=" + value
                    except AttributeError:
                        pass
                self.tags[nice_tag].append(unicode(value))
    def save_tags(self, tags=None):
        raise NotImplementedError
        mf = self.mutagen_file
        # first, examine which tags are to be deleted
        for tag in mf.tags:
            if mf.tags[tag].FrameID in ID3_IGNORE or tag in ID3_IGNORE:
                continue
            elif ID3_MAPPING[tag] not in tags:
                del mf[tag]
        
        for tag in tags.keys():
            pass
            
        
 
class EasyFile(TagFile):
    def __init__(self,path):
        TagFile.__init__(self,path)
        if self.mutagen_file.tags==None:
            print("File '{0}' has _no_ tags!".format(path))
        else:
            for tag,value in self.mutagen_file.tags:
                if not tag.lower() in self.tags:
                    self.tags[tag.lower()] = []
                self.tags[tag.lower()].append(value)
    
    def save_tags(self, tags=None):
        if tags==None:
            tags = self.tags
        self.mutagen_file.clear()
        for key in tags.keys():
            self.mutagen_file[key] = tags[key]
        self.mutagen_file.save()

class ApeFile(TagFile):
    def __init__(self,path):
        TagFile.__init__(self,path)
        f = self.mutagen_file
        for tag in f.tags:
            value = f.tags[tag].value.decode("utf-8")
            if tag in APE_MAPPING:
                tag = APE_MAPPING[tag]
            if not tag.lower() in self.tags:
                self.tags[tag.lower()] = []
            self.tags[tag.lower()].append(value)
            
class MP4File(TagFile):
    def __init__(self,path):
        TagFile.__init__(self, path)
        f = self.mutagen_file
        for tag in f.keys():
            if tag in MP4_IGNORE:
                self.ignored.append(tag)
                continue
            try:
                nice_tag = MP4_MAPPING[tag]
            except KeyError as e:
                print("Error reading file '{0}'".format(path))
                raise e
            for value in f[tag]:
                if value=="":
                    continue
                if tag == "trkn":
                    self.tags["tracknumber"] = [ value[0] ]
                    self.tags["tracktotal"] = [ value[1] ]
                elif tag=="disk":
                    self.tags["discnumber"] = [ value[0] ]
                    self.tags["disctotal"] = [ value[1] ]
                else:
                    if not nice_tag in self.tags:
                        self.tags[nice_tag] = []
                    self.tags[nice_tag].append(value)
                
def File(path):
    extension = path.rsplit(".",1)[1].lower()
    if extension=="mp3":
        return MP3File(path)
    elif extension in ["flac", "ogg", "spx"]:
        return EasyFile(path)
    elif extension=="mpc": #APE
        return ApeFile(path)
    elif extension in ["mp4", "m4a"]:
        return MP4File(path)
