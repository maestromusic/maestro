# -*- coding: utf-8 -*-
# Copyright 2010 Michael Helmling
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

import logging
from omg import distributor

logger = logging.getLogger("plugins.dbupdatedebugger")

def enable():
    distributor.indicesChanged.connect(handleSignal)
    
def disable():
    distributor.indicesChanged.disconnect(handleSignal)
    
def handleSignal(notice):
    logger.debug("{}DB update notice for ids {}".format("Recursive " if notice.recursive else '',notice.ids))
