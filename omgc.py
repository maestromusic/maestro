#!/usr/bin/env python3.1
# -*- coding: utf-8 -*-
# Copyright 2009 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
# omgc.py

import getopt
import sys
import db
import constants
import os.path

def usage():
    print("""Usage: {0} options [path]

Valid options are:
    -h, --help:       Print this help message
    -l, --list:       List all containers that are not a file.
    -i <id>, --id=id: List contents of container with the given id.
    -p, --populate:   Populate your database. If path is given, walk through all subdirectories
                      of that path, else use the collection entry in your config file.
    --reset:          Totally resets your database (use with caution!)
    --check:          Check database integrity.
                
""".format(os.path.basename(sys.argv[0])))

if __name__=="__main__":
    opts, args = getopt.getopt(sys.argv[1:], "phli:", ['help', 'list','populate','reset','check','id='])
    if len(opts) == 0:
        usage()
        sys.exit()
    db.connect()
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
            finder = populate.find_new_albums(path)
            for album in finder:
                populate.do_album(album)
        
        elif opt in ("--reset"):
            if input("Warning: This will reset your _complete_ database! Are you sure!?") in constants.YES_ANSWERS:
                db.reset()
            else:
                print("Aborting reset.")
                
        elif opt in ("--check"):
            try:
                db.check_tables
            except db.DatabaseLayoutException as e:
                print(e)
                if input("Fix?") in constants.YES_ANSWERS:
                    db.check_tables(create_tables=True, insert_tagids=True)
            broken_fkeys = db.check_foreign_keys()
            if broken_fkeys > 0:
                if input("There are {0} broken foreign keys. Correct this?".format(broken_fkeys)) in constants.YES_ANSWERS:
                    db.check_foreign_keys(autofix=True)
        
        elif opt in ("-i", "--id"):
            cid = int(arg)
            print_container(cid)
