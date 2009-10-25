#!/usr/bin/env python2.6
# -*- coding: utf-8 -*-
"""This script is used for passing tags to and from python3.1 programs. Normally the data
is passed in a pickled via pipes. The pickled object should be a dictionary, which has the keys
"tags", leading to another dictionary, and perhaps "length" which leads an integer (in seconds)."""

import sys
import tags26
import getopt
import pickle
import os.path
import re

def usage():
    print("""Usage: {cmd} <mode> [options] files

Currently supported modes:
    pickle: Write pickled tags to stdout
    text: Write tags in textform to stdout
    store: Store tags in file, obtained from stdin as pickled dictionary.
    regex: Modify tags with regular expressions (needs further options, see below)
    
Options:
  Options for mode regex:
    -t, --tag: In which tag to do the replacements
    -s, --search=<expr>: The search expression
    -r, --replace=<expr>: The replace expression
    -d, --dry: dry run
    
""".format(cmd=os.path.basename(sys.argv[0])))

MODES = ("pickle", "text", "store", "regex")

def output(cmdline,mode="text"):
    opts, args = getopt.getopt(cmdline, "")
    for path in args:
        f = tags26.File(path)
        if mode=="text":
            print("Tags of file: '{0}'".format(path))
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

def store(cmdline):
    """Stores the tags given in "data" in the given file."""
    opts, args = getopt.getopt(cmdline, "")
    if len(args) != 1:
        print("I can only store tags to exactly one file at once.")
        sys.exit(1)
    path = args[0]
    data = pickle.load(sys.stdin)
    f = tags26.File(path)
    f.save_tags(data["tags"])

def regex_tag_replace(path,tag,search,replace,dry):
    file = tags26.File(path)
    if tag not in file.tags:
        print("Warning: Skipping file '{0}' which has no tag {1}".format(path,tag))
        return
    result = re.sub(search,replace,file.tags[tag][0])
    if result != file.tags[tag][0]:
        print(u"{f}: '{old}' -> '{new}'".format(f=path.decode("utf-8"),old=file.tags[tag][0],new=result))
        if not dry:
            file.tags[tag][0] = result
            file.save_tags()
def regex(cmdline):
    """Performs regular expression based string substitution in tags."""
    opts, args = getopt.getopt(cmdline, "dRs:r:t:", ("search=","replace=","dry","tag=","recursive"))
    search = replace = tag = None
    dry = recursive = False
    for o,a in opts:
        if o in ("-s", "--search"):
            search = a
        elif o in ("-r", "--replace"):
            replace = a
        elif o in ("-d", "--dry"):
            dry = True
        elif o in ("-t", "--tag"):
            tag = a
        elif o in ("-R", "--recursive"):
            recursive = True
    if search==None or replace==None or tag==None:
        print("You need to supply the search, replace and tag options.")
        sys.exit(1)
    for arg in args:
        if os.path.isdir(arg):
            if recursive:
                for dirpath,subdirs,filenames in os.walk(arg):
                    for f in sorted(filenames):
                        regex_tag_replace(os.path.join(dirpath,f), tag, search, replace, dry)
                
        else:
            regex_tag_replace(arg,tag,search,replace,dry)

            
if __name__=="__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in MODES:
        usage()
        sys.exit(1)
    mode = sys.argv[1]
    if mode=="text":
        output(sys.argv[2:], mode="text")
    elif mode=="pickle":
        output(sys.argv[2:], mode="pickle")
    elif mode=="store":
        store(sys.argv[2:])
    elif mode=="regex":
        regex(sys.argv[2:])
