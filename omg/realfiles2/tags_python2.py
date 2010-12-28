#!/usr/bin/env python2
# -*- coding: utf-8 -*-
# Copyright 2010 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
#

"""
This Python 2-script is used to read and write tags using Mutagen. It is invoked in a subprocess of the main application (which is written in Python 3) and communicates with the main process via stdout, stdin and after exceptions stderr.

During its runtime this script waits for pickled data on stdin and prints pickled results to stdout. The data must be a dict containing at least the two keys 'command' with one of the following commands and 'path' with an absolute path to the file to which the command should be applied. These commands are defined:

'read': Write a (pickled) dict to stdout containing the keys 'length' (the length as float) and 'tags' (the tags as dict). Note that this script does not know omg's distinction into indexed and ignored tags and will return all tags from the file (unless the file is an MP3 where many frames are ignored regardless of all configuration files  just because reading them is not implemented).

'keys': Write a (pickled) list containing all keys of tags in the file to stdout.

'remove': In this case the data must contain a third key 'tags' which points to a list of tag-names. These tags will be removed from the file. Tags in the list which do not not exist in the file are skipped without notice.

'store': This command expects a key 'tags' in data, too. That key must point to a dict of tags and these tags will be written to the file. To be precise: For each tag in tags exactly the values of that tag will be stored in the file (removing all other values). The other tags remain untouched (you have to use 'remove' to get rid of them).

Note that all commands write pickled output to stdout. If something went wrong, they will write a (pickled) 1 and stderr will contain error information. If everything went fine the commands which do not have an actual result (i.e. remove and store) will write a 0.

The tags-module is not used by this script and hence incoming and outgoing tags will be dicts mapping tag-names to lists of tag-values. These tag-values must always be strings (also for date, tracknumber, etc.).
"""

import sys, pickle
from mutagen import id3

import frames
from frames import FRAMES

COMMANDS = ["read","keys","store","remove"]

def createFile(path):
    """Create a file for the given path. This method will look for the extension and if that doesn't help will use mutagen.File(path) to guess the type, which is much slower."""
    if path.rfind('.') != -1:
        ext = path.rsplit(".",1)[1].lower()
        if ext in ['mp3','mp2','mpg','mpeg']:
            return Mp3File(path)
        elif ext in ['ogg','flac','spx']:
            return EasyFile(path)
        elif ext == 'mpc': #APE
            return ApeFile(path)
        elif ext in ['mp4','m4a']:
            return Mp4File(path)
    # Let mutagen guess the filetype. This is much slower
    file = mutagen.File(path)
    if file.__class__.name____ == 'MP3':
        return Mp3File(path,file=file)
    elif file.__class__.__name__ in ['OggVorbis','FLAC','OggSpeex']:
        return EasyFile(path,file=file)
    elif file.__class__.__name__ == 'APEv2':
        return ApeFile(path,file=file)
    elif file.__class__.__name__ == 'MP4':
        return Mp4File(path,file=file)

    raise IOError("Cannot open file '{}'".format(path))
    

class File:
    """Abstract base class for the various File classes."""

    def keys(self):
        """Return the list of tagnames which are contained in this file."""
        raise NotImplementedError()
        
    def read(self):
        """Return the list of tagnames which are contained in this file."""
        raise NotImplementedError()

    def remove(self,tagList):
        """Remove the tags in <tagList> from this file. Skip tags which don't exist in the file."""
        raise NotImplementedError()

    def store(self,tags):
        """Store the given tags in this file: For each key in <tags> store exactly the values <tags[key]>, removing all other values. Leave the other tags unchanged."""
        raise NotImplementedError()


class EasyFile(File):
    """File implementation for easy filetypes (most notably .ogg and .flac). There is not much to do here..."""

    def __init__(self,path,file=None):
        """Create an EasyFile-instance for the given path, or if <path> is None, just use <file> as internal Mutagen-file. In the first case, the path must have a valid extension."""
        self.path = path
        ext = path.rsplit(".",1)[1].lower()
        if file is not None:
            self._file = file
        else:
            if ext == 'flac':
                from mutagen.flac import FLAC
                self._file = FLAC(path)
            elif ext == 'ogg':
                from mutagen.oggvorbis import OggVorbis
                self._file = OggVorbis(path)
            elif ext == 'spx':
                from mutagen.oggspeex import OggSpeex
                self._file = OggSpeex(path)
            else: raise ValueError("ext must be one of 'flac', 'ogg', or 'spx'.")

    def read(self):
        length = self._file.info.length
        if self._file.tags is None:
            tags = {}
        else: tags = dict(self._file.tags)
        return {'length': length, 'tags': tags}

    def keys(self):
        return list(self._file.keys())

    def remove(self,tagList):
        for tag in tagList:
            if tag in self._file:
                del self._file[tag]
        self._file.save()

    def store(self,tags):
        for tag,values in tags.items():
            self._file[tag] = values
        self._file.save()
        

class Mp3File(File):
    """This subclass of File reads MP3-files. Well, actually Mutagen does the hardest work and it remains to convert between ID3-frames and nice tagnames as used in music programs."""
    def __init__(self,path,file=None):
        """Create an EasyFile-instance for the given path, or if <path> is None, just use <file> as internal Mutagen-file."""
        if file is None:
            from mutagen.mp3 import MP3
            self._file = MP3(path)
        else: self.file = _file
        if self._file.tags is None:
            self._file.add_tags()
        self._tags = self._file.tags

    def _getTXXXName(self,description):
        """Get the nice tagname which should be used for a TXXX-frame with the given description. Usually that is just the description."""
        if description.startswith(u'QuodLibet::'):
            return description[11:]
        else: return description
        
    def _tagGenerator(self,ignoredFrames=None,unknownFrames=None):
        """This generator filters the tags contained in self._file and returns a tuple (frame,values) for the rest (frame is an instance of frame.Frames contained in frames.FRAMES; values is a list of strings). The generator filters frames, which are ignored or unknown, away and replaces TXXX- and WXXX-frames by their nice names (basically their description)."""
        for key,frameObject in self._tags.items():
            # Warning: Keys may be as complicated as 'TXXX:QuodLibet::mycustomtag'
            # Thus we have to split the key first
            if len(key) > 4:
                assert isinstance(key,unicode)
                assert key[4] == u':'
                description = key[5:] # Get rid of the colon
                key = key[:4]
            else:
                assert isinstance(key,str)
                description = None

            if key not in FRAMES:
                if unknownFrames is not None:
                    unknownFrames.add(key)
                continue
            
            frame = FRAMES[key]
            if frame.type in (frames.IGNORE,frames.INFO):
                #TODO Do something in the INFO case
                if ignoredFrames is not None:
                    ignoredFrames.add(key)
                continue
                
            # All other frames should have a text object which is a list of the values
            assert hasattr(frameObject,'text') and isinstance(frameObject.text,list)
            values = frameObject.text

            # Replace TXXX and WXXX frames by their descriptions
            if key == u'TXXX' or key == u'WXXX':
                frame.name = self._getTXXXName(description)

            assert frame.name is not None
            yield frame,values

    def keys(self):
        return [frame.name for frame,values in self._tagGenerator()]

    def read(self):
        tags = {}
        for frame,values in self._tagGenerator():
            # Replace timestamps
            if frame.type == frames.TIME:
                values = [value.get_text() if isinstance(value,id3.ID3TimeStamp) else value for value in values]
            # Never export a Mutagen-object because the main application will then try to load Mutagen.
            assert all(isinstance(value,unicode) for value in values)
            tags[frame.name] = values
        return {'length': self._file.info.length,'tags': tags}

    def _tagToKeys(self,tag):
        """Return a list of all frame-keys which exist in the current file and would be converted to <tag> during reading. For tag='artist', this list would contain 'TPE1', 'TXXX:artist' and 'TXXX:QuodLibet::artist' if these keys were all present in this file."""
        result = []
        if tag in frames.REVERSED and frames.REVERSED[tag] in self._tags:
            result.append(frames.REVERSED[tag])

        # Always look whether TXXX and WXXX contains a frame which would be transformed to <name>-tags in _getTXXXName
        for frame in self._tags:
            if frame.startswith(u'TXXX') or frame.startswith(u'WXXX'):
                description = frame[5:] # Chop of 'TXXX:'
                if self._getTXXXName(frame[5:]) == tag:
                    result.append(frame)
        return result
        
    def remove(self,tagList):
        for name in tagList:
            for key in self._tagToKeys(name):
                del self._tags[key]
        self._file.save()

    def store(self,tags):
        for tagKey,values in tags.items():
            assert isinstance(tagKey,unicode)
            # First create the frame where we will store these values
            if tagKey in frames.REVERSED:
                frameKey = frames.REVERSED[tagKey]
                frame = id3.__dict__[frameKey](text=values,encoding=3) # Always use UTF-8
            else:
                #TODO: Use other frames if possible (e.g. COMM, WXXX)
                frameKey = u'TXXX:'+tagKey
                frame = id3.TXXX(text=values,desc=tagKey,encoding=3) # Always use UTF-8

            # After this method our file must contain exactly the given values for this tag-key.
            # Thus we have to remove all other frames which would be converted to tagKey in self.read.
            # This will for example remove a TXXX:QuodLibet::description-frame when writing a TXXX:description-frame.
            for key in self._tagToKeys(tagKey):
                if key != frameKey:
                    del self._tags[key]

            # Next step is to convert the values:
            #TODO: watch for values which cannot be written to the file in restricted frames like TIME and URL

            # Finally write to the file
            self._tags.add(frame)
            self._file.save()


class ApeFile(File):
    pass


class Mp4File(File):
    pass


if __name__=="__main__":
    try:
        while True: # process will be terminated by the main application
            data = pickle.load(sys.stdin)
            if data['command'] not in COMMANDS:
                raise ValueError("Unknown command: {}".format(data['command']))
            file = createFile(data['path'])
            result = None
            if data['command'] == 'read':
                result = file.read()
            elif data['command'] == 'keys':
                result = file.keys()
            elif data['command'] == 'store':
                file.store(data['tags'])
            elif data['command'] == 'remove':
                file.remove(data['tags'])

            if result is None:
                # pickle is waiting for a result at the other end of the pipe, hence we have to print something
                result = 0
            pickle.dump(result,sys.stdout)
            sys.stdout.flush()
    except Exception as e:
        print >> sys.stderr, "Error in subprocess: ", type(e), str(e)
        pickle.dump(1,sys.stdout) # Error
        sys.exit(1)
