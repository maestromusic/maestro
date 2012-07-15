# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2012 Martin Altmayer, Michael Helmling
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

import os.path
import functools, itertools, collections
import urllib.parse
import xml.dom.minidom

from PyQt4 import QtCore,QtGui,QtNetwork
from PyQt4.QtCore import Qt

from ...core import tags, covers
from ...core.elements import Element
from ... import application

translate = QtCore.QCoreApplication.translate

LASTFM_API_KEY = 'b25b959554ed76058ac220b7b2e0a026'
LASTFM_SIZES = ["small","medium","large","extralarge","mega"]
   

def enable():
    covers.providerClasses.append(LastFMCoverProvider)
    
    
def disable():
    covers.providerClasses.remove(LastFMCoverProvider)
    

class LastFMCoverProvider(covers.AbstractCoverProvider):
    """CoverProvider that fetches covers using Last.fm's REST-API."""
    def __init__(self):
        super().__init__()
        self.xmlReplies = collections.defaultdict(list)
        self.imageReplies = collections.defaultdict(list)
        
    @classmethod
    def name(cls):
        return translate("LastFMCoverFetcher","Last.fm")
    
    @classmethod
    def icon(cls):
        return QtGui.QIcon(":omg/lastfm.gif")
    
    def fetch(self,elements):
        for element in elements:
            urls = self._getLastFmURLs(element)
            if len(urls) == 0:
                self.error.emit(self.tr("Cannot fetch a cover for an element without artist or album."))
                self.finished.emit(element)
            else:
                for url in urls:
                    reply = application.network.get(QtNetwork.QNetworkRequest(url))
                    reply.finished.connect(functools.partial(self._handleXmlReplyFinished,element,reply))
                    reply.error.connect(functools.partial(self._handleNetworkError,reply))
                    self.xmlReplies[element].append(reply)
    
    def _getLastFmURLs(self,element):
        """Based on *element*'s artist-tags and album-tags, return a list of URLs where album information
        including cover URLs may be found.""" 
        urls = []
        for artist,album in itertools.product(element.tags[tags.get('artist')],element.tags[tags.ALBUM]):
            url = QtCore.QUrl('http://ws.audioscrobbler.com/2.0/')
            url.addQueryItem('method','album.getinfo')
            url.addQueryItem('artist',artist)
            url.addQueryItem('album',album)
            url.addQueryItem('api_key',LASTFM_API_KEY)
            urls.append(url)
            print(url.toString())
        return urls
        
    def _handleNetworkError(self,reply):
        """Handle the error-signal of all QNetworkReplies."""
        self.error.emit(self.tr("Network error: {}").format(reply.errorString()))
        
    def _getURLsFromXml(self,xmlData):
        """Get cover URLs from XML returned by Last.fm's API. *xmlData* must be a string."""
        try:
            document = xml.dom.minidom.parseString(xmlData)
        except: # documentation doesn't tell what exceptions are to be expected
            raise RuntimeError()
                
        # Last.fm delivers covers in different sizes. We collect all of them and use the biggest
        # size we can find
        sizeDict = collections.defaultdict(list)
        lfm = document.firstChild
        if lfm.getAttribute('status') != 'ok':
            raise RuntimeError()
        for albumNode in lfm.childNodes:
            if isinstance(albumNode,xml.dom.minidom.Element) and albumNode.tagName == 'album':
                for node in albumNode.childNodes:
                    if isinstance(node,xml.dom.minidom.Element) and node.tagName == 'image'\
                            and node.firstChild != None:
                        size = node.getAttribute('size')
                        if size in LASTFM_SIZES:
                            sizeDict[size].append(QtCore.QUrl(node.firstChild.data))
        for size in reversed(LASTFM_SIZES):
            if size in sizeDict:
                return sizeDict[size]
        else: return []
        
    def _handleXmlReplyFinished(self,element,reply):
        """React to finished XML replies. These replies do not contain the covers but information about
        the album in Last.fm's XML-format. This method will get the cover URLs from XML and start new
        requests for them.""" 
        try:
            if reply.error() != QtNetwork.QNetworkReply.NoError:
                # an error occured and has been handled by _handleNetworkError
                return 
            urls = self._getURLsFromXml(reply.readAll())
            for url in urls:
                imageReply = application.network.get(QtNetwork.QNetworkRequest(url))
                imageReply.finished.connect(functools.partial(self._handleImageReplyFinished,
                                                              element,imageReply))
                imageReply.error.connect(functools.partial(self._handleNetworkError,imageReply))
                self.imageReplies[element].append(imageReply)
        except RuntimeError: # parsing xml failed
            url = reply.request().url().toString()
            self.error.emit("Cannot fetch cover URL from XML at '{}'.".format(url))
        finally:
            self.xmlReplies[element].remove(reply)
            self._checkFinished(element)
                        
    def _handleImageReplyFinished(self,element,reply):
        """React to finished image replies. These replies really contain image data. So create a QPixmap
        from them and emit the loaded-signal."""
        try:
            if reply.error() != QtNetwork.QNetworkReply.NoError:
                # an error occured and has been handled by _handleNetworkError
                return
            pixmap = QtGui.QPixmap()
            if not pixmap.loadFromData(reply.readAll()):
                url = reply.request().url().toString()
                self.error.emit(self.tr("Could not load cover image from '{}'.").format(url))
                return
            
            self.loaded.emit(element,pixmap)
        finally:
            self.imageReplies[element].remove(reply)
            self._checkFinished(element)
        
    def _checkFinished(self,element):
        """This is called when a reply for *element* is finished and emits the finished-signal if that reply
        was the last one for this element."""
        if len(self.xmlReplies[element]) == 0 and len(self.imageReplies[element]) == 0:
            self.finished.emit(element)
        