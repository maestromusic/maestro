#!/usr/bin/env python2.6
# -*- coding: utf-8 -*-
"""This script is used for passing tags to and from python3.1 programs. Normally the data
is passed in a pickled via pipes. The pickled object should be a dictionary, which has the keys
"tags", leading to another dictionary, and perhaps "length" which leads an integer (in seconds)."""

import sys
import tags26
import getopt
import pickle


def output(path,mode="text"):
    f = tags26.File(path)
    if mode=="text":
        for tag in f.tags:
            print(tag)
            for value in f.tags[tag]:
                print(u"   {0}".format(value))
        print("Length of the file: {0}".format(f.length))
    elif mode=="pickle":
        out = { "tags":f.tags, "length":f.length}
        pickle.dump(out, sys.stdout)
    else:
        raise ValueError("Output Mode '{0}' not known".format(mode))

def store(path, data):
    """Stores the tags given in "data" in the given file."""
    f = tags26.File(path)
    f.save_tags(data["tags"])
    
if __name__=="__main__":
    opts, args = getopt.getopt(sys.argv[1:], "pst",("pickle", "text", "store"))
    mode = "text"
    if len(args) != 1:
        print("Error: There must be exactly one non-option argument, which is the audio file to use.")
        sys.exit(1)
    path = args[0]
    for o,a in opts:
        if o in ('-t', "--text"):
            mode = "text"
        elif o in ('-p', "--pickle"):
            mode = "pickle"
        elif o in ('-s', "--store"):
            mode= "store"
    
    if mode=="text":
        output(path, mode="text")
    elif mode=="pickle":
        output(path, mode="pickle")
    elif mode=="store":
        data = pickle.load(sys.stdin)
        store(path,data)
