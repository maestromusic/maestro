# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2013-2014 Martin Altmayer, Michael Helmling
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""This module contains the file identifier providers - ffmpeg/md5 and acoustid."""

import hashlib
import os, subprocess
import sys

from .. import logging
logger = logging.getLogger(__name__)

_logOSError = True

class AcoustIDIdentifier:
    """An identifier using the AcoustID fingerprinter and web service.
    
    First, the fingerprint of a file is generated using the "fpcalc" utility which must be
    installed. Afterwards, an API lookup is made to find out the AcoustID track ID. If the
    AcoustID database contains an associated MusicBrainz ID, that one is preferred. The returend
    strings are prepended by "acoustid:" or "mbid:" to distinguish the two cases.
    
    In case the AcoustID lookup fails, an md5 hash of the first 15 seconds of raw audio is used
    for identifying the file.
    """
      
    requestURL = ("http://api.acoustid.org/v2/lookup?"
                  "client={}&meta=recordingids&duration={}&fingerprint={}")
    
    def __init__(self, apikey):
        self.apikey = apikey
        self.null = open(os.devnull)
        
    def __call__(self, url):
        try:
            data = subprocess.check_output(['fpcalc', url.absPath])
        except OSError as e: # fpcalc not found, not executable etc.
            global _logOSError
            if _logOSError:
                _logOSError = False # This error will always occur  - don't print it again.
                logger.warning(e)
            return self.fallbackHash(url)
        except subprocess.CalledProcessError as e:
            # fpcalc returned non-zero exit status
            logger.warning(e)
            return self.fallbackHash(url)
        data = data.decode(sys.getfilesystemencoding())
        if len(data) == 0:
            logger.warning("fpcalc did not return any data")
            return self.fallbackHash(url)
        duration, fingerprint = (line.split("=", 1)[1] for line in data.splitlines()[1:] )
        import urllib.request, urllib.error, json
        try:
            req = urllib.request.urlopen(self.requestURL.format(self.apikey, duration, fingerprint))
        except urllib.error.HTTPError as e:
            logger.warning(e)
            logger.warning(self.requestURL.format(self.apikey, duration, fingerprint))
            return self.fallbackHash(url)
        ans = req.readall().decode("utf-8")
        req.close()
        ans = json.loads(ans)
        if ans['status'] != 'ok':
            logger.warning("Error retrieving AcoustID fingerprint for {}".format(url))
            return self.fallbackHash(url)
        results = ans['results']
        if len(results) == 0:
            logger.warning("No AcoustID fingerprint found for {}".format(url))
            return self.fallbackHash(url)
        bestResult = max(results, key=lambda x: x['score'])
        if "recordings" in bestResult and len(bestResult["recordings"]) > 0:
            ans = "mbid:{}".format(bestResult["recordings"][0]["id"])
            logger.debug("found mbid={} for {}".format(ans, url))
        else:
            ans = "acoustid:{}".format(bestResult["id"])
            logger.debug("found acoustid={} for {}".format(ans, url))
        return ans

    def fallbackHash(self, url):
        """Compute the audio hash of a single file using ffmpeg to dump the audio.
        
        This method uses the "ffmpeg" binary ot extract the first 15 seconds in raw PCM format and
        then creates the MD5 hash of that data.
        """
        logger.warning("Using fallback FFMPEG method")
        try:
            proc = subprocess.Popen(['ffmpeg', '-i', url.absPath, '-v', 'quiet',
                                     '-f', 's16le', '-t', '15', '-'],
                                    stdout=subprocess.PIPE,
                                    stderr=self.null)
        except OSError:
            logger.warning('ffmpeg not installed - could not compute fallback audio hash.')
            return None
        data = proc.stdout.read()
        proc.wait()
        hash = hashlib.md5(data).hexdigest()
        return "hash:{}".format(hash)
