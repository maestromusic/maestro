#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-

import mpd
import time
HOST_1 = "localhost"
PORT_1 = "6600"

HOST_2 = "jukebox"
PORT_2 = "6600"

client1 = mpd.MPDClient()
client2 = mpd.MPDClient()

client1.connect(host=HOST_1, port=PORT_1)
client2.connect(host=HOST_2, port=PORT_2)

playlist = client1.playlist()
client2.clear()
for file in playlist:
    client2.add(file)

def convert_to_seconds(timestring):
    parts = timestring.split(":")
    if len(parts) > 1:
        result = int(parts[-2])
    if len(parts) > 2:
        result += 60*int(parts[-3])
    if len(parts) > 3:
        result += 3600*int(parts[-4])
    print("{0}->{1}".format(timestring,result))
    return result

status = client1.status()
if status["state"] == "stop":
    pass
else:
    client2.play()
    time.sleep(1)
    client1.seek(status['song'], convert_to_seconds(status['time'])+1)
    client2.seek(status['song'], convert_to_seconds(status['time'])+1)