#!/usr/bin/env python2.6
# -*- coding: utf-8 -*-

import mutagen

ID3_MAPPING = {
    "TIT2" : "TITLE",
    "TPE1" : "ARTIST",
    "TPE2" : "PERFORMER",
    "TPE3" : "CONDUCTOR",
    "TRCK" : "TRACKNUMBER",
    "TDRC" : "DATE",
    "TCON" : "GENRE",
    "TCOM" : "COMPOSER",
    "TALB" : "ALBUM",
    "TEXT" : "LYRICIST",
    "TIT3" : "VERSION",
    "COMM" : "DESCRIPTION",
    "TPOS" : "DISCNUMBER",
}