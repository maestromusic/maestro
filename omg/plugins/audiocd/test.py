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

discid = "ivDUEtXkT85jToKhK0uyAfLGIco-" # rhapsody
#discid = "9swiFyYNN2LEsRtPHmiGa_jhfzA-" # 111 CD 2

from omg.plugins.musicbrainz import xmlapi
from omg import application
from omg.core import levels
application.run(type='console')

releases = xmlapi.findReleasesForDiscid(discid)
print("FOUND RELEASES:")
for release in releases:
    print(release.pprint())

ans = 1    
#ans = int(input("Which one to follow? "))

release = releases[ans]
container = xmlapi.makeReleaseContainer(release, discid, levels.editor)
print(container)
