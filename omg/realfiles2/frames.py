#!/usr/bin/env python2
# -*- coding: utf-8 -*-
# Copyright 2010 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
#

"""Frame data for the tags_python2-script."""

# Types
IGNORE, INFO, TEXT, ROTEXT, SPECIAL, POS, TIME, URL = range(1,9)

# Frames data (this will be converted into an object-oriented version below)
# Note that all frames which are not of type IGNORE, INFO or SPECIAL must have a name as third element in the tuple.
FRAMES = {
'AENC': (u"Audio encryption",                        IGNORE),
'APIC': (u"Attached picture",                        INFO),
'ASPI': (u"Audio seek point index",                  IGNORE),
'COMM': (u"Comments",                                INFO),
'COMR': (u"Commercial frame",                        IGNORE),
'ENCR': (u"Encryption method registration",          IGNORE),
'EQU2': (u"Equalisation",                            IGNORE),
'ETCO': (u"Event timing codes",                      INFO),
'GEOB': (u"General encapsulated object",             INFO),
'GRID': (u"Group identification registration",       IGNORE),
'LINK': (u"Linked information",                      IGNORE),
'MCDI': (u"Music CD identifier",                     INFO),
'MLLT': (u"MPEG location lookup table",              IGNORE),
'OWNE': (u"Ownership frame",                         IGNORE),
'PRIV': (u"Private frame",                           INFO),
'PCNT': (u"Play counter",                            IGNORE),
'POPM': (u"Popularimeter",                           IGNORE),
'POSS': (u"Position synchronisation frame",          IGNORE),
'RBUF': (u"Recommended buffer size",                 IGNORE),
'RVA2': (u"Relative volume adjustment (2)",          IGNORE),
'RVRB': (u"Reverb",                                  IGNORE),
'SEEK': (u"Seek frame",                              IGNORE),
'SIGN': (u"Signature frame",                         IGNORE),
'SYLT': (u"Synchronised lyric/text",                 INFO),
'SYTC': (u"Synchronised tempo codes",                IGNORE),
'TALB': (u"Album/Movie/Show title",                  TEXT,       u"album"),
'TBPM': (u"BPM (beats per minute)",                  TEXT,       u"bpm"),
'TCOM': (u"Composer",                                TEXT,       u"composer"),
# Note that mutagen automatically translates numbers to genres as defined at http://www.id3.org/id3v2.3.0
'TCON': (u"Content type",                            TEXT,       u"genre"),
'TCOP': (u"Copyright message",                       TEXT,       u"copyright"),
'TDLY': (u"Playlist delay",                          IGNORE), # Could be handled
'TDOR': (u"Original release time",                   TIME,       u"original release time"),
'TDRC': (u"Recording time",                          TIME,       u"date"),
'TDRL': (u"Release time",                            TIME,       u"releasetime"),
'TDTG': (u"Tagging time",                            IGNORE),
'TENC': (u"Encoded by",                              TEXT,       u"encodedby"),
'TEXT': (u"Lyricist/Text writer",                    TEXT,       u"lyricist"),
'TFLT': (u"File type",                               IGNORE),
'TIPL': (u"Involved people list",                    INFO),
'TIT1': (u"Content group description",               TEXT,       u"content group"),
'TIT2': (u"Title/songname/content description",      TEXT,       u"title"),
'TIT3': (u"Subtitle/Description refinement",         TEXT,       u"subtitle"),
'TKEY': (u"Initial key",                             ROTEXT,     u"initial key"),
'TLAN': (u"Language(s)",                             ROTEXT,     u"language"),
'TLEN': (u"Length",                                  IGNORE),
'TMCL': (u"Musician credits list",                   INFO),
'TMED': (u"Media type",                              TEXT,       u"media type"),
'TMOO': (u"Mood",                                    TEXT,       u"mood"),
'TOAL': (u"Original album/movie/show title",         TEXT,       u"original album"),
'TOFN': (u"Original filename",                       TEXT,       u"original filename"),
'TOLY': (u"Original lyricist(s)/text writer(s)",     TEXT,       u"original lyricist"),
'TOPE': (u"Original artist(s)/performer(s)",         TEXT,       u"original artist"),
'TOWN': (u"File owner/licensee",                     TEXT,       u"owner"),
'TPE1': (u"Lead performer(s)/Soloist(s)",            TEXT,       u"artist"),
'TPE2': (u"Band/orchestra/accompaniment",            TEXT,       u"performer"),
'TPE3': (u"Conductor/performer refinement",          TEXT,       u"conductor"),
'TPE4': (u"Interpreted, remixed, or otherwise modified by",TEXT, u"arranger"),
'TPOS': (u"Part of a set",                           POS,        u"discnumber"),
'TPRO': (u"Produced notice",                         TEXT,       u"produced notice"),
'TRCK': (u"Track number/Position in set",            POS,        u"tracknumber"),
'TRSN': (u"Internet radio station name",             TEXT,       u"internet radio station name"),
'TRSO': (u"Internet radio station owner",            TEXT,       u"internet radio station owner"),
'TSOA': (u"Album sort order",                        TEXT,       u"album sort order"),
'TSOP': (u"Performer sort order",                    TEXT,       u"performer sort order"),
'TSOT': (u"Title sort order",                        TEXT,       u"title sort order"),
'TSRC': (u"ISRC (international standard recording code)",TEXT,   u"isrc"),
'TSSE': (u"Software/Hardware and settings used for encoding",TEXT,u"settings used for encoding"),
'TSST': (u"Set subtitle",                            TEXT,       u"set subtitle"),
'TXXX': (u"User defined text information frame",     SPECIAL),
'UFID': (u"Unique file identifier",                  IGNORE),
'USER': (u"Terms of use",                            IGNORE),
'USLT': (u"Unsynchronised lyric/text transcription", INFO),
'WCOM': (u"Commercial information",                  URL,        u"commercial information"),
'WCOP': (u"Copyright/Legal information",             URL,        u"copyright"),
'WOAF': (u"Official audio file webpage",             URL,        u"file webpage"),
'WOAR': (u"Official artist/performer webpage",       URL,        u"artist webpage"),
'WOAS': (u"Official audio source webpage",           URL,        u"audio source webpage"),
'WORS': (u"Official Internet radio station homepage",URL,        u"internet radio station homepage"),
'WPAY': (u"Payment",                                 URL,        u"payment webpage"),
'WPUB': (u"Publishers official webpage",             URL,        u"publishers webpage"),
'WXXX': (u"User defined URL link frame",             SPECIAL)
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

REVERSED = {}
# No dictionary comprehensions in Python 2 :-(
for k,v in FRAMES.items():
    if v.name is not None:
        REVERSED[v.name] = k
