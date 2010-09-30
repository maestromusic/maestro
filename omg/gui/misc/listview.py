#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2010 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#
from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

class ListView(QtGui.QListView):
    """Listview which pays attention to its contents when calculating sizeHints and does not use scrollbars. The sizeHint-method of QListView is inherited all the way down from QAbstractScrollArea...and it returns the hard-coded value (256,192). Confer QTBUG-2273, QTBUG-6118 and QTBUG-2338."""
    def __init__(self,parent=None):
        QtGui.QListView.__init__(self,parent)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    
    def minimumSizeHint(self):
        extra = 2* self.frameWidth()
        
        # The following code is from qabstractscrollarea.cpp, but it leads to a scrollarea that is slightly too large.
        opt = QtGui.QStyleOption()
        opt.initFrom(self)
        if (self.frameStyle() != QtGui.QFrame.NoFrame
              and self.style().styleHint(QtGui.QStyle.SH_ScrollView_FrameOnlyAroundContents,opt,self)):
            extra = extra + self.style().pixelMetric(QtGui.QStyle.PM_ScrollView_ScrollBarSpacing,opt,self)
    
        return QtCore.QSize(self.sizeHintForColumn(0)+extra,
                            sum(self.sizeHintForRow(i) for i in range(self.model().rowCount()))+extra)
    
    def sizeHint(self):
        return self.minimumSizeHint()