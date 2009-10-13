#!/usr/bin/env python2.6
# -*- coding: utf-8 -*-

import sys
import tags
import getopt
import pickle


if __name__=="__main__":
    opts, args = getopt.getopt(sys.argv[1:], "tp")
    write_text = False
    write_pickle = True
    for o,a in opts:
        if o=='-t':
            write_text = True
            write_pickle = False
        elif o=='-p':
            write_pickle=True
            write_text = False
    f = tags.File(args[0])
    tags = f.tags
    if write_text:
        for tag in tags:
            print(tag)
            for value in tags[tag]:
                print(u"  {0}".format(value))
    if write_pickle:
        print(pickle.dumps(tags))
    