#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-
# Copyright 2009 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
# omgc.py

import omg
import getopt
import sys

def usage():
    print("""See source code for usage info :-p""")
    
if __name__=="__main__":
    opts, args = getopt.getopt(sys.argv[1:], "ph", ['help', 'populate'])
    
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit()
        elif opt in ("-p", "--populate"):
            if len(args) == 0:
                import config
                path = config.get("music","collection")
            else:
                path = args[0]
            import populate
            populate.walk(path)
