#!/usr/bin/python2.6
# -*- coding: utf-8 -*-

import tags
import sys
import os.path
import os

def clean(file):
    f = tags.File(file)
    if len(f.ignored) > 0:
        
        print(u"Found fucking tags:")
        print(file)
        for i in f.ignored:
            if i.startswith("APIC"):
                print("   <picture>")
                continue
            try:
                print(u"   {0}={1}".format(unicode(i),unicode(f.mutagen_file[i])))
            except UnicodeDecodeError:
                print(u"   {0}".format(i))
        ans = raw_input("Delete? [Yn]")
        print(ans)
        ok_answers=["y","Y","j","J",""]
        if ans in ok_answers:
            f.delete_ignored()

if __name__=="__main__":
   
    if os.path.isdir(sys.argv[1]):
        for dirpath,dirnames,filenames in os.walk(sys.argv[1]):
            for f in filenames:
                clean(os.path.join(dirpath,f))
    else:
        clean(sys.argv[1])
