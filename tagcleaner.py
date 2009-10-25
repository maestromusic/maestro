#!/usr/bin/python2.6
# -*- coding: utf-8 -*-

import tags26
import sys
import os.path
import os
import getopt
modes = ("empty", "ignored")
yes_directory=None
def clean_ignored(file,autoclean=False):
    global yes_directory
    try:
        f = tags26.File(file)
    except tags26.UnsupportedFileExtension:
        print("Unknown file: '{0}'".format(file))
        return
    if len(f.ignored) > 0:
        
        print(u"Found fucking tags:")
        print(file)
        for i in f.ignored:
            if i.startswith("APIC"):
                print("   <picture>")
                continue
            try:
                print(u"   {0}".format(unicode(f.mutagen_file[i].pprint())))
            except UnicodeDecodeError:
                print(u"   {0}".format(i))
        if autoclean or os.path.dirname(file)==yes_directory:
            f.delete_ignored()
        else:
            ans = raw_input("Delete? (Yes/No/All in this directory) [Yna]")
            print(ans)
            ok_answers=["y","Y","j","J","", "a", "A"]
            if ans in ok_answers:
                f.delete_ignored()
            if ans in ["a", "A"]:
                yes_directory=os.path.dirname(file)

def clean_empty(file, autoclean=False):
    global yes_directory
    try:
        f = tags26.File(file)
    except tags26.UnsupportedFileExtension:
        print("Unknown file: '{0}'".format(file))
        return
    for tag in list(f.tags.keys()):
        if f.tags[tag][0] == "":
            print("Empty tag '{0}' in file '{1}'".format(tag, file))
            if autoclean or os.path.dirname(file)==yes_directory:
                del f.tags[tag]
                f.save_tags()
            else:
                ans = raw_input("Delete? (Yes/No/All in this directory) [Yna]")
                ok_answers=["y","Y","j","J","", "a", "A"]
                if ans in ok_answers:
                    del f.tags[tag]
                    f.save_tags()
                if ans in ["a", "A"]:
                    yes_directory=os.path.dirname(file)


if __name__=="__main__":
    opts, args = getopt.getopt(sys.argv[1:], ("ye"))
    YES = False
    mode = "ignored"
    for o,a in opts:
        if o == "-y":
            YES = True
        elif o == "-e":
            mode = "empty"
    if mode=="ignored":
        if os.path.isdir(args[0]):
            for dirpath,dirnames,filenames in os.walk(args[0]):
                for f in filenames:
                    clean_ignored(os.path.join(dirpath,f),autoclean=YES)
        else:
            clean_ignored(args[0])
    elif mode=="empty":
        if os.path.isdir(args[0]):
            for dirpath,dirnames,filenames in os.walk(args[0]):
                for f in filenames:
                    clean_empty(os.path.join(dirpath,f),autoclean=YES)
        else:
            clean_empty(args[0])
