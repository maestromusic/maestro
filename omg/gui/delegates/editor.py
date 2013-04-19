# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2013 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtCore

from . import profiles, StandardDelegate

translate = QtCore.QCoreApplication.translate


class EditorDelegate(StandardDelegate):
    """Delegate for the editor."""

    profileType = profiles.createProfileType(
            name      = 'editor',
            title     = translate("Delegates","Editor"),
            leftData  = ['t:album','t:composer','t:artist','t:performer'],
            rightData = ['t:date','t:genre','t:conductor'],
            overwrite = {'showPaths': True,
                         'showType': True,
                         'appendRemainingTags': True,
                         'showAllAncestors': True}
    )
