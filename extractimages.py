#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
# Module / standalone-script to extract images from the APIC-ID3-tag to a given folder and (optionally) delete them from the mp3-files.
#
import sys
import getopt
import os
from mutagen.id3 import ID3

def usage():
    print("""
Usage: python extractimages.py [options] file/directory ...
This little script extracts all images from the given mp3-files and from all mp3-files in the given directories (and all subdirectories).
Options:
-h,--help: Prints this help message
-o,--output=[dir]: Specifies the directory in which the images will be saved. Defaults to the current working directory.
--delete: After extracting, images tags will be deleted from the original mp3-file. Use with care...
""")


def extract(path,output,delete=False):
    """Extracts all images from mp3-files in <path> (may be a file or a directory) to the directory <output>. If <delete> is True the image tags will be deleted from the mp3-files after extracting."""
    if not os.path.isdir(output):
        raise Exception("extractimages.extract: Output directory must be a directory.")
    if os.path.isfile(arg):
        _process_file(arg,output,delete)
    elif os.path.isdir(arg):
        for path,subdirs,files in os.walk(arg):
            for f in files:
                _process_file(os.path.join(path,f),output,delete)


def _process_file(path,output,delete):
    """Extracts all images from the given file <path> to the directory <output>. If <delete> is True the image tags will be deleted from the mp3-file after extracting."""
    if not path.lower().endswith(".mp3"):
        return
    try:
        mp3file = ID3(path)
        for frame in mp3file.getall("APIC"):
            filename = os.path.join(output,os.path.basename(path)[:-4]) # Strip the .mp3-extension
            if os.path.exists(filename):
                counter = 1
                while os.path.exists(filename + "_{0}".format(counter)):
                    counter = counter + 1
                filename = filename + "_{0}".format(counter)

            # It remains to add the extension
            extension = ".img"
            if frame.mime in ("image/jpeg","image/jpg"):
                extension = ".jpg"
            if frame.mime == "image/png":
                extension = ".png"
            if frame.mime == "image/gif":
                extension = ".gif"
            filename = filename + extension

            print("Writing image to " + filename)
            imgfile = file(filename,"wb")
            imgfile.write(frame.data)
            imgfile.close()

            if delete:
                print("Deleting APIC tags from "+path)
                mp3file.delall("APIC")
                mp3file.save()

    except KeyboardInterrupt: raise
    except Exception, err: print str(err)


if __name__=="__main__":
    output = os.getcwd() # Images will be extracted in this folder
    delete = False # Should image tags be deleted from the mp3-files?
    try:
        options,args = getopt.getopt(sys.argv[1:],"o:h",("output=","delete","help"))
    except getopt.GetoptError, err:
        print str(err)
        usage()
        sys.exit(2)

    for option,value in options:
        if option in ("-h","--help"):
            usage()
            sys.exit(1)
        elif option in ("-o","--output"):
            output = os.path.expanduser(value)
        elif option == "--delete":
            delete = True

    if not os.path.isdir(output):
        print("Output directory must be a directory...")
        sys.exit(2)

    for arg in args:
        extract(os.path.expanduser(arg),output,delete)