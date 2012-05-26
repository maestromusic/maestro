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

from .. import database as db
from ..core import levels
from ..core.nodes import RootNode, Wrapper
 

class Sequence:
    """A sequence of adjacent files. Basically this is simply a closed integral interval [*start*,*end*].
    The length of a sequence is the number of files in it.
    """
    def __init__(self,start,end):
        assert start <= end
        self.start = start
        self.end = end
        
    def __len__(self):
        return self.end - self.start + 1
    
    def bounded(self,other):
        """Return the subsequence of this sequence that is contained in the sequence *other*. If that
        subsequence is empty, return None. Example: Sequence(2,7).bounded(Sequence(0,5)) = Sequence(2,5).
        """
        start = max(other.start,self.start)
        end = min(other.end,self.end)
        if start <= end:
            return Sequence(start,end)
        else: return None
        
    def __repr__(self):
        return "[{},{}]".format(self.start,self.end)
    

class SequenceDict(dict):
    """A dict mapping element ids to sequences of files that are descendants of the element.
    
    On creation the dict will create lists for each file in *files* and for all of their ancestors (in the
    given level). Each list will be populated with the sequences of descendants of that element, i.e. ranges
    of adjacent files in *files* that are descendants of the element.
    
    For example: If *files* contains 5 files of which the first three are in the container with id 1
    and the last two are in the container with id 2 and both containers are in a third container with id 3,
    then the dict would contain the mappings {1: [Sequence(0,2)], 2: [Sequence(3,4)], 3: [Sequence(0,4)]}
    and also a mapping for each file: The i-th file's id is mapped to [Sequence(i,i)].
    
    For *preWrapper* and *postWrapper* see buildTree. All wrapper ancestors of these wrappers will be also
    added to the dict (with sequences in the negative numbers for *preWrapper* parents and sequences with
    start >= len(files) for *postWrapper* parents. These wrappers are not used to build the tree but their
    sequences leads to parents of *preWrapper* and *postWrapper* being favored.
    
    Furthermore this dict has an attribute toplevelIds storing a list of all toplevel ancestors of *files*
    (including the ids of files which do not have any ancestor).
    """
    def __init__(self,level,files,preWrapper,postWrapper):
        super().__init__()
        self.level = level
        self.toplevelIds = []
        
        # First add the parents and sequences of preWrapper, then the parents/sequences of the files in their
        # order and finally the parents/sequences of postWrapper. The order is important so that merging
        # of sequences works (whenever a new sequence is added it is only compared to last sequence of the
        # corresponding element).  
        if preWrapper is not None:
            last = preWrapper
            for parent in preWrapper.getParents():
                if isinstance(parent,Wrapper):
                    self.add(parent.element.id,-parent.fileCount(),-1)
                    last = parent
                else: break
            self.toplevelIds.append(last.element.id)
                
        for i,file in enumerate(files):
            self._addFileToElement(file.id,i)
            
        if postWrapper is not None:
            last = postWrapper
            for parent in postWrapper.getParents():
                if isinstance(parent,Wrapper):
                    self.add(parent.element.id,len(files)+1,len(files)+parent.fileCount())
                    last = parent
                else: break
            if last.element.id not in self.toplevelIds:
                self.toplevelIds.append(last.element.id)
            
        #print("SEQ: {}".format({self.level.get(id).getTitle(): seq for id,seq in self.items()}))
        #print("TIDs: {}".format(self.toplevelIds))
            
    def add(self,id,start,end=None):
        """Add a sequence [*start*,*end*] to the list of sequences of the element given by *id*. If the
        sequence comes directly after the last sequence of this element, extend that last sequence instead
        of adding a new one.
        """ 
        if end is None:
            end = start
        if id not in self:
            self[id] = [Sequence(start,end)]
        else:
            lastSeq = self[id][-1]
            if lastSeq.end >= start - 1:
                lastSeq.end = max(lastSeq.end,end)
            else: self[id].append(Sequence(start,end))
            
    def _addFileToElement(self,elementId,fileIndex):
        """Add a Sequence [*fileIndex*,*fileIndex*] to the element with id *elementId* and recursively to
        all of its ancestors. Try to merge the sequences like in self.add.
        
        Also update the attribute toplevelIds.
        """
        self.add(elementId,fileIndex)
        element = self.level.get(elementId)
        if len(element.parents) == 0:
            if element.id not in self.toplevelIds:
                self.toplevelIds.append(element.id)
        else:
            for id in self.level.get(elementId).parents:
                self._addFileToElement(id,fileIndex)
                
    def longest(self,ids,boundingSequence=None):
        """Search for a longest sequence in this dict. Only search in the lists of the elements given by
        the ids *ids* and if *boudingSequence* is not None, compare sequences not by their real length but by
        the length of the sequences bounded to *boundingSequence*.
        
        Return a tuple consisting of a longest sequence (bounded to *boundingSequence*) and the element
        (not the id) there that sequence was found.
        """
        longest = None
        element = None
        for id in ids:
            if id not in self:
                continue
            for seq in self[id]:
                if boundingSequence is not None:
                    seq = seq.bounded(boundingSequence)
                if seq is not None and (longest is None or len(seq) > len(longest)):
                    longest = seq
                    element = self.level.get(id)
        return longest, element
     
    def remove(self,sequence):
        """Remove the given sequence from all sequences in this dict, i.e. remove sequences that are
        completely contained in *sequence* and shrink sequences that overlap with *sequence*.
        """
        for id in list(self.keys()):
            newSeqs = []
            for seq in self[id]:
                if seq.end < sequence.start or seq.start > sequence.end:
                    # No overlap: Simply keep the sequence
                    newSeqs.append(seq)
                else:
                    # Note that the next two if's may both be True. In this case we split seq into two
                    # new sequences (this happens if sequence ⊂ seq).
                    if seq.start < sequence.start:
                        newSeqs.append(Sequence(seq.start,sequence.start - 1))
                    if seq.end > sequence.end:
                        newSeqs.append(Sequence(sequence.end+1,seq.end))
            if len(newSeqs):
                self[id] = newSeqs
            else: del self[id]
            
    def contains(self,id,sequence):
        """Return whether the sequences of the element with id *id* contain a sequence that contains
        *sequence*."""
        return any(s.start <= sequence.start and s.end >= sequence.end for s in self[id])
             
        
def buildTree(level,wrappers,parent=None,preWrapper=None,postWrapper=None):
    """Build a tree over the given list of wrapper return its root wrappers as list.
    If possible add containers to the tree to generate a nice tree structure. This method is for example
    used by the playlist to generate a nice tree playlist from a simple list of files.
    
    *level* is the level that determines the possible tree structure.
    
    *preWrapper* and *postWrapper* specify the file-wrapper before and after the new tree if the tree is e.g.
    to be inserted into a playlist. When building the container structure, ancestors of these wrappers in the
    existing tree structure are favored. Existing Wrappers will not be changed, though. It is the task of
    the caller to merge wrappers returned by this method and existing wrappers.
    
    TODO: comment parent
    """
    #print("PARENT/PRE/POST: {} {} {}".format(parent,preWrapper,postWrapper))
    if len(wrappers) == 0:
        return []
    seqs = SequenceDict(level,[w.element for w in wrappers],preWrapper,postWrapper)

    # If a parent is given and it contains all elements that should be inserted, then accept only the
    # contents of this parent as toplevel nodes
    while not isinstance(parent,RootNode):
        if parent.element.id in seqs and seqs.contains(parent.element.id,Sequence(0,len(wrappers)-1)):
            toplevelIds = parent.element.contents.ids
            break
        parent = parent.parent
    else: toplevelIds = seqs.toplevelIds
        
    return _buildTree(wrappers,seqs,None,toplevelIds)

    
def _buildTree(wrappers,seqs,boundingSeq,toplevelIds):
    """Build a tree over the part of *files* specified by *boundingSeq* (over all files if *boundingSeq* is
    None. *seqs* is the SequenceDict, *toplevelIds* are the elements that may be used at the highest level.
    """
    # Root nodes are not necessarily added in correct order. Insert them indexed by the start point of their
    # sequence and at the end sort them by the start point.
    roots = {}
    
    while True:
        # Choose the longest sequence (bounded to boundingSeq and only from elements within toplevelIds)
        # The second restriction increases performance and avoids that we accidentally choose a child when
        # its parent has the same sequence (this happens only for single children).
        longestSeq,element = seqs.longest(toplevelIds,boundingSeq)
        if longestSeq is None:
            # All wrappers in *boundingSeq* are covered
            break
        
        # Skip sequences that are completely out of range (this may happen due to preWrapper/postWrapper)
        if longestSeq.end < 0 or longestSeq.start >= len(wrappers):
            seqs.remove(longestSeq)
            continue
        
        # Create a wrapper for the tree...or use the one that was submitted
        if len(longestSeq) == 1 and element == wrappers[longestSeq.start].element:
            wrapper = wrappers[longestSeq.start]
        else:
            wrapper = Wrapper(element)
            if wrapper.isContainer():
                # For containers recursively create the tree below. Bound the tree creation to longestSeq.
                # Choose only roots which are contents of element.
                childContents = _buildTree(wrappers,seqs,longestSeq,element.contents.ids)
                wrapper.setContents(childContents)
        
        # Add the wrapper to roots and remove the sequence from all sequences
        roots[longestSeq.start] = wrapper
        seqs.remove(longestSeq)
    
    # Sort root nodes by start point
    return [roots[key] for key in sorted(roots.keys())]
   