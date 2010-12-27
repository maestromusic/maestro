#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2010 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
#

# Types
IGNORE, INFO, TEXT, ROTEXT, SPECIAL, POS, TIME, URL = range(1,9)

# Frames data (this will be converted into an object-oriented version below)
# Note that all frames which are not of type IGNORE, INFO or SPECIAL must have a name as third element in the tuple.
FRAMES = {
'AENC': ("Audio encryption",                        IGNORE),
'APIC': ("Attached picture",                        INFO),
'ASPI': ("Audio seek point index",                  IGNORE),
'COMM': ("Comments",                                INFO),
'COMR': ("Commercial frame",                        IGNORE),
'ENCR': ("Encryption method registration",          IGNORE),
'EQU2': ("Equalisation",                            IGNORE),
'ETCO': ("Event timing codes",                      INFO),
'GEOB': ("General encapsulated object",             INFO),
'GRID': ("Group identification registration",       IGNORE),
'LINK': ("Linked information",                      IGNORE),
'MCDI': ("Music CD identifier",                     INFO),
'MLLT': ("MPEG location lookup table",              IGNORE),
'OWNE': ("Ownership frame",                         IGNORE),
'PRIV': ("Private frame",                           INFO),
'PCNT': ("Play counter",                            IGNORE),
'POPM': ("Popularimeter",                           IGNORE),
'POSS': ("Position synchronisation frame",          IGNORE),
'RBUF': ("Recommended buffer size",                 IGNORE),
'RVA2': ("Relative volume adjustment (2)",          IGNORE),
'RVRB': ("Reverb",                                  IGNORE),
'SEEK': ("Seek frame",                              IGNORE),
'SIGN': ("Signature frame",                         IGNORE),
'SYLT': ("Synchronised lyric/text",                 INFO),
'SYTC': ("Synchronised tempo codes",                IGNORE),
'TALB': ("Album/Movie/Show title",                  TEXT,       "album"),
'TBPM': ("BPM (beats per minute)",                  TEXT,       "bpm"),
'TCOM': ("Composer",                                TEXT,       "composer"),
'TCON': ("Content type",                            TEXT,       "genre"),
'TCOP': ("Copyright message",                       TEXT,       "copyright"),
'TDLY': ("Playlist delay",                          IGNORE), # Could be handled
'TDOR': ("Original release time",                   TIME,       "original release time"),
'TDRC': ("Recording time",                          TIME,       "date"),
'TDRL': ("Release time",                            TIME,       "releasetime"),
'TDTG': ("Tagging time",                            IGNORE),
'TENC': ("Encoded by",                              TEXT,       "encodedby"),
'TEXT': ("Lyricist/Text writer",                    TEXT,       "lyricist"),
'TFLT': ("File type",                               IGNORE),
'TIPL': ("Involved people list",                    INFO),
'TIT1': ("Content group description",               TEXT,       "content group"),
'TIT2': ("Title/songname/content description",      TEXT,       "title"),
'TIT3': ("Subtitle/Description refinement",         TEXT,       "subtitle"),
'TKEY': ("Initial key",                             ROTEXT,     "initial key"),
'TLAN': ("Language(s)",                             ROTEXT,     "language"),
'TLEN': ("Length",                                  IGNORE),
'TMCL': ("Musician credits list",                   INFO),
'TMED': ("Media type",                              TEXT,       "media type"),
'TMOO': ("Mood",                                    TEXT,       "mood"),
'TOAL': ("Original album/movie/show title",         TEXT,       "original album"),
'TOFN': ("Original filename",                       TEXT,       "original filename"),
'TOLY': ("Original lyricist(s)/text writer(s)",     TEXT,       "original lyricist"),
'TOPE': ("Original artist(s)/performer(s)",         TEXT,       "original artist"),
'TOWN': ("File owner/licensee",                     TEXT,       "owner"),
'TPE1': ("Lead performer(s)/Soloist(s)",            TEXT,       "artist"),
'TPE2': ("Band/orchestra/accompaniment",            TEXT,       "performer"),
'TPE3': ("Conductor/performer refinement",          TEXT,       "conductor"),
'TPE4': ("Interpreted, remixed, or otherwise modified by",TEXT, "arranger"),
'TPOS': ("Part of a set",                           POS,        "discnumber"),
'TPRO': ("Produced notice",                         TEXT,       "produced notice"),
'TRCK': ("Track number/Position in set",            POS,        "tracknumber"),
'TRSO': ("Internet radio station name",             TEXT,       "internet radio station name"),
'TRSO': ("Internet radio station owner",            TEXT,       "internet radio station owner"),
'TSOA': ("Album sort order",                        TEXT,       "album sort order"),
'TSOP': ("Performer sort order",                    TEXT,       "performer sort order"),
'TSOT': ("Title sort order",                        TEXT,       "title sort order"),
'TSRC': ("ISRC (international standard recording code)",TEXT,   "isrc"),
'TSSE': ("Software/Hardware and settings used for encoding",TEXT,"settings used for encoding"),
'TSST': ("Set subtitle",                            TEXT,       "set subtitle"),
'TXXX': ("User defined text information frame",     SPECIAL),
'UFID': ("Unique file identifier",                  IGNORE),
'USER': ("Terms of use",                            IGNORE),
'USLT': ("Unsynchronised lyric/text transcription", INFO),
'WCOM': ("Commercial information",                  URL,        "commercial information"),
'WCOP': ("Copyright/Legal information",             URL,        "copyright"),
'WOAF': ("Official audio file webpage",             URL,        "file webpage"),
'WOAR': ("Official artist/performer webpage",       URL,        "artist webpage"),
'WOAS': ("Official audio source webpage",           URL,        "audio source webpage"),
'WORS': ("Official Internet radio station homepage",URL,        "internet radio station homepage"),
'WPAY': ("Payment",                                 URL,        "payment webpage"),
'WPUB': ("Publishers official webpage",             URL,        "publishers webpage"),
'WXXX': ("User defined URL link frame",             SPECIAL)
}

class Frame:
    def __init__(self,key,data):
        self.key = key
        if len(data) == 2:
            self.officialName,self.type = data
            self.name = None
        else: self.officialName,self.type,self.name = data


for key,data in FRAMES.items():
    FRAMES[key] = Frame(key,data)

REVERSED = {v.name: k for k,v in FRAMES.items() if v.name is not None}
