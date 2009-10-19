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
import db

def usage():
    print("""See source code for usage info :-p""")
    
if __name__=="__main__":
    opts, args = getopt.getopt(sys.argv[1:], "phl", ['help', 'list','populate'])
    
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit()
        elif opt in ("-l", "--list"):
            print("Here is a list of non-file containers in my database:")
            print("{0:>5}: {1}".format("id", "name"))
            print("------------------------------------------------------")
            result = db.query('SELECT container_id,name,count(element_id) FROM containers INNER JOIN contents ON containers.id=container_id group by container_id')
            for id, name, elements in result:
                print("{0:5d}: {1} ({2} Elements)".format(id, name, elements))
        elif opt in ("-p", "--populate"):
            if len(args) == 0:
                import config
                path = config.get("music","collection")
            else:
                path = args[0]
            import populate
            populate.walk(path)
