#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from PyQt4 import QtGui

from omg import strutils, tags, covers
from omg.models import playlist
from . import delegate

_stdCharFormat = QtGui.QTextCharFormat()
_stdCharFormat.setFontPointSize(10)

_titleCharFormat = QtGui.QTextCharFormat()
_titleCharFormat.setFontPointSize(10)
_titleCharFormat.setFontWeight(QtGui.QFont.Bold)

_artistCharFormat = QtGui.QTextCharFormat()
_artistCharFormat.setFontPointSize(10)
_artistCharFormat.setFontWeight(QtGui.QFont.Bold)
_artistCharFormat.setFontItalic(True)

_tableFormat = QtGui.QTextTableFormat()
_tableFormat.setBorderStyle(QtGui.QTextFrameFormat.BorderStyle_None)
_tableFormat.setWidth(QtGui.QTextLength(QtGui.QTextLength.PercentageLength,100))
_tableFormat.setCellSpacing(0)
_tableFormat.setCellPadding(0)

class PlaylistLayouter():
    def layout(self,element):
        if isinstance(element,playlist.ExternalFile):
            return delegate.SingleLineLayout(element.getPath(),["italic"])
        
        if element.isFile():
            if element.getPosition() is None:
                titleString = element.getTitle()
            else: titleString = "{0} - {1}".format(element.getPosition(),element.getTitle())
            return delegate.TwoColumnsLayout(titleString,strutils.formatLength(element.getLength()))
        else:
            return delegate.ContainerLayout(element)