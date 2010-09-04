#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
import cgi

from omg import config,covers,models,strutils,tags
import datetime

class Formatter:
    """A Formatter takes an element and offers several functions to get formatted output from the tags, length, title etc. of the element."""
    def __init__(self,element):
        """Create a formatter for the given element."""
        self.element = element
    
    def tagValues(self,tag,removeParentTags=False,getTags=None):
        if removeParentTags: # Filter away tags which appear in a parent container
            if getTags is None:
                getTags = self._getTags
            values = list(getTags(self.element,tag)) # copy the list to avoid removing tags from the original container
            parent = self.element.getParent()
            while parent is not None:
                for value in getTags(parent,tag):
                    if value in values:
                        values.remove(value)
                parent = parent.getParent()
            return values
        else: return self.element.tags[tag]
        
    def tag(self,tag,removeParentTags=False,getTags=None):
        """Return a string containing all values of the given tag in the element of this formatter. Depending on the tag the values will be separated either by ", " or by " - ". If removeParentTags is True all values of <tag> in parent containers of the current tree structure will be removed from the result. To fetch tag-values from a parent container the method <getTags> is used. The default function returns the tag-values of <tag> if the parent container is an Element and an empty list else, which is usually exactly what you want. But if your tree contains nodes not of type Element but still with tags, you must provide your own function to get those tags. <getTags> must take a node and <tag> and must return a list of tag-values."""
        values = self.tagValues(tag,removeParentTags,getTags)
        if tag == tags.TITLE or tag == tags.ALBUM:
            sep = " - "
        else: sep = ", "
        if tag == tags.DATE:
            return sep.join(date.strftime("%Y") if isinstance(date,datetime.date) else str(date) for date in values)
        else: return sep.join(values)

    def _getTags(self,node,tag):
        """Help function for tag: Return the values of the given tag of <node> if <node> is an Element and an empty list otherwise."""
        if isinstance(node,models.Element):
            return node.tags[tag]
        else: return []
        
    def title(self):
        """Return the title or some dummy-title if the element contains no title."""
        if tags.TITLE in self.element.tags:
            result = " - ".join(self.element.tags[tags.TITLE])
        else: result = "<Kein Titel>"
        if isinstance(self.element,models.Element) and config.get("misc","show_ids"):
            return "[{0}] {1}".format(self.element.id,result)
        else: return result

    def album(self):
        """Return a string containing the album names, but if the element is an album itself or is contained in an album, remove it from the list. If you just want the album tags, use Formatter.tag(tags.ALBUM)."""
        if tags.ALBUM in self.element.tags: # There is at least one album
            albums = self.tagValues(tags.ALBUM,True)

            if self.element.isContainer():
                # In the first iteration check whether the element is an album itself. Don't do this for files as it is quite common to have a song with the same name as its album.
                parent = self.element
            else: parent = self.element.getParent()
            while isinstance(parent,models.Element):
                for title in parent.tags[tags.TITLE]:
                    try:
                        albums.remove(title)
                    except ValueError: pass
                parent = parent.getParent()
            return " - ".join(albums)       
        return ""    
        
    def titleWithPos(self):
        """Return a string containing the position (if any) and the title."""
        if self.element.getPosition() is not None:
            return "{0} - {1}".format(self.element.getPosition(),self.title())
        else: return self.title()
    
    def length(self):
        """Return the formatted length of the element."""
        length = self.element.getLength()
        if length is not None:
            return strutils.formatLength(self.element.getLength())
        else: return ""

    def files(self):
        """Return the formatted number of files in the element."""
        fileCount = self.element.getFileCount()
        if fileCount == 1:
            return "{0} Stück".format(fileCount)
        else: return "{0} Stücke".format(fileCount)


class HTMLFormatter(Formatter):
    """HTMLFormatter creates a detailed HTML-view of an element, displaying all tags and an album cover."""
    def __init__(self,element):
        """Create an HTMLFormatter for the given element."""
        Formatter.__init__(self,element)

    def detailView(self):
        """Return HTML-code which renders a detailed view of the element."""
        lines = []
        self.element.ensureTagsAreLoaded()
        coverPath = None
        if isinstance(self.element, models.Element):
            coverPath = covers.getCoverPath(self.element.id,config.get("gui","detail_cover_size"))
            if coverPath is not None:
                lines.append('<table><tr><td valign="top"><img src="{0}"></td><td valign="top">'
                                .format(cgi.escape(coverPath)))
        else:
            lines.append('<i>External file</i>')
        lines.append('<div style="font-size: 14px; font-weight: bold">{0}</div>'.format(cgi.escape(self.title())))
        if tags.ALBUM in self.element.tags:
            lines.append('<div style="font-size: 14px; font-weight: bold; font-style: italic">{0}</div>'
                            .format(cgi.escape(self.tag(tags.ALBUM))))

        # Create a div around the remaining tag values
        lines.append('<div style="font-size: 12px">')
        
        tagLines = []
        for tag in [t for t in tags.tagList if t in self.element.tags and t != tags.TITLE and t != tags.ALBUM]:
            tagLines.append('{0}: {1}'.format(cgi.escape(str(tag)),cgi.escape(self.tag(tag))))

        lines.append("<br>".join(tagLines))
        lines.append('</div>')
        if coverPath is not None:
            lines.append('</td></tr></table>')
            
        return "".join(lines)