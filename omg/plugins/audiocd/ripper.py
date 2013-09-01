# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2013 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtCore, QtGui
import tempfile
import os
import subprocess

class RipThread(QtCore.QThread):
    
    trackFinished = QtCore.pyqtSignal(str, int, str)
    
    def __init__(self, device, discid):
        super().__init__()
        self.device = device
        self.discid = discid
        
    def run(self):
        tmpdir = tempfile.mkdtemp(prefix='omg_rip')
        subprocess.call(["cdparanoia", "-q", "-B", "-d", self.device, "1"], cwd=tmpdir)
        tracks = sorted(os.listdir(tmpdir))
        for i, track in enumerate(tracks, 1):
            subprocess.call(["flac", track], cwd=tmpdir)
            flactrack = track[:-3] + "flac"
            print('track encoded: {}'.format(flactrack))
            self.trackFinished.emit(self.discid, i, os.path.join(tmpdir, flactrack))
            
if __name__ == "__main__":
    import sys
    app = QtCore.QCoreApplication(sys.argv)
    th = RipThread("/dev/cdrom", "1234")
    th.start()
    app.exec_()