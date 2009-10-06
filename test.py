#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-
import mpd
import sys
m = mpd.MPDClient()
m.connect(host="localhost", port="6600")

searchstring = sys.argv[1]
results = m.search("any", searchstring)
albums = {}
for r in results:
        album = r["album"]
        if not album in albums:
            albums[album] = []
        albums[r["album"]].append(r["file"])
for alb in albums.keys():
    print(alb)
    for f in albums[alb]:
        print("    {0}".format(f))