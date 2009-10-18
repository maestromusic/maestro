# -*- coding: utf-8 -*-


class TagDict(dict):
    """Special dictionary that also has a length attribute. Used for file tags."""
    
    def __init__(self):
        dict.__init__(self)
        self.length=-1
