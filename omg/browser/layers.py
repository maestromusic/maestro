#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

class TagLayer():
    DIRECT_LOAD_LIMIT = 100
    
    def __init__(self,tagSet):
        self.tagSet = tagSet
        self.nextLayer = None
        
class ContainerLayer(): pass