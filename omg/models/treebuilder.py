#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2009 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
#

class ContainerNode:
    """The TreeBuilder-algorithm creates a ContainerNode for each ancestor of the items. During the algorithm these nodes store the following information:
    id: The container-ID of this ancestor
    items: The items which are (directly) contained in this container
    childContainers: The ContainerNodes for the containers which are directly contained in this container
    itemSequences: List of item-sequences of this container
    parentIds: A list of IDs of this container's parents
    """
    
    def __init__(self,id):
        """Initialize a new ContainerNode with the given id."""
        self.id = id
        self.items = []
        self.childContainers = []
        self.itemSequences = []
        self.parentIds = None
    
    # For debugging
    def __str__(self):
        itemString = "[{0}]".format(",".join(str(item) for item in self.items))
        childContainerString = "[{0}]".format(",".join(str(c.id) for c in self.childContainers))
        return "ContainerNode {0}:\n\tItems {1}\n\tChildContainers {2}\n\tItemSequences {3}\n\tParentIds {4}".format(self.id,itemString,childContainerString,self.itemSequences,self.parentIds)


class TreeBuilder:
    """This class encapsulates an algorithm that - given a list of items and information in what containers these items are contained - builds a tree structure covering all nodes in a nice way."""
    def __init__(self,getId,getParentIds,createNode,insertIntoNode):
        """Intialize the algorithm with two methods:
        - get an item and return its id (or None if it doesn't has an id)
        - getParentIds takes an ID of an item or a container and returns a list of the IDs of all parent containers.
        - createNode takes a container-ID and a list of children (which may be items or containers previously created with this method), creates a new node and returns it.
        """
        self._getId = getId
        self._getParentIds = getParentIds
        self._createNode = createNode
        self._insertIntoNode = insertIntoNode
    
    def build(self,items):
        """Build a tree over the given items."""
        self.items = items
        self.containerNodes = {}
        
        # First step: Build a graph of all items and containers.
        for i in range(0,len(items)):
            self._buildContainerNodes(items[i])
            self._updateItemSequences(items[i],i)
        
        # Debug after the first step
        #for node in self.containerNodes.values():
        #    print(node)
        
        # Second step: Choose optimal container structure for the given items
        roots = self._createTree((0,len(items)-1),self.containerNodes.values())
        
        # Free unused variables
        del self.items
        del self.containerNodes
        
        return roots

    def insert(self,node,pos,items):
        self.containerNodes = {}
        self.items = items
        
        for i in range(0,len(items)):
            self._buildContainerNodes(items[i])
            self._updateItemSequences(items[i],i)
            
        # Debug after the first step
        #for n in self.containerNodes.values():
        #    print(n)
            
        self._insert(node,pos,(0,len(items)-1),self.containerNodes.values())
        
        # Free variables
        del self.containerNodes
    
    def _insert(self,node,pos,sequence,cNodes):
        print("This is _insert for node {0} at pos {1} and with sequence {2}".format(node,pos,sequence))
            
        # Items will be inserted between these two items
        if pos > 0:
            prev = node.getChildren()[pos-1]
        else: prev = None
        if pos < node.getChildrenCount():
            next = node.getChildren()[pos]
        else: next = None
        print("prev: {0}".format(prev))
        print("next: {0}".format(next))
        
        startSeq = None
        endSeq = None
        if prev is not None and self._getId(prev) is not None and self._getId(prev) in self.containerNodes:
            prevCNode = self.containerNodes[self._getId(prev)]
            for seq in prevCNode.itemSequences:
                if seq[0] == sequence[0]:
                    startSeq = seq
                    # Yeah: The previous node contains some of the first items
                    self._insert(prev,prev.getChildrenCount(),startSeq,prevCNode.childContainers)
                    break
        
        if next is not None and self._getId(next) is not None and self._getId(next) in self.containerNodes:
            nextCNode = self.containerNodes[self._getId(next)]
            for seq in nextCNode.itemSequences:
                if seq[1] == sequence[1]:
                    endSeq = seq
                    # Yeah: The next node contains some of the last items
                    self._insert(next,0,endSeq,nextCNode.childContainers)
                    break
                
        # It may happen that startSeq and endSeq overlap. In this case we shrink endSet.
        if startSeq is not None and endSeq is not None and startSeq[1] >= endSeq[0]:
            endSeq = (startSeq[1] + 1,endSeq[1])
            if self._seqLen(endSeq) < 1:
                endSeq = None
            
        # Get the remaining items
        remSeqStart = sequence[0] if startSeq is None else startSeq[1]+1
        remSeqEnd = sequence[1] if endSeq is None else endSeq[0]-1
        remainingSequence = (remSeqStart,remSeqEnd)
        if self._seqLen(remainingSequence) > 0:
            self._insertIntoNode(node,pos,self._createTree(remainingSequence,cNodes))
        
    def _buildContainerNodes(self,node):
        """If they do not exist already, create ContainerNodes for all ancestors of the given node.
        
        For all parent containers of the given node a ContainerNode is created if it doesn't already exists and the  given node is added to the children list of the ContainerNode. Whenever a new node is created, this method is recursively called on the new node, to create all ancestors of that node."""
        
        # Get list of parent-ids
        if isinstance(node,ContainerNode):
            listOfPids = node.parentIds
        else: 
            itemId = self._getId(node)
            if itemId is None: # This node has no id, so it must not have parent nodes
                return
            else: listOfPids = self._getParentIds(self._getId(node))
        
        for pid in listOfPids:
            # If no ContainerNode for this pid exists, create one
            if pid not in self.containerNodes:
                self.containerNodes[pid] = ContainerNode(pid)
                self.containerNodes[pid].parentIds = self._getParentIds(pid)
                # Recursive call to create all ancestors of the new node
                self._buildContainerNodes(self.containerNodes[pid])
            
            # Append the node to the children of the parent container
            if isinstance(node,ContainerNode):
                self.containerNodes[pid].childContainers.append(node)
            else: self.containerNodes[pid].items.append(node)


    def _updateItemSequences(self,node,itemIndex):
        """Update the item-sequences of <node> and all its ancestors to contain the item with index <itemIndex>."""
        # Get list of parent-ids
        if isinstance(node,ContainerNode):
            listOfPids = node.parentIds
        else:
            itemId = self._getId(node)
            if itemId is None: # This node has no id, so it must not have parent nodes
                return
            else: listOfPids = self._getParentIds(self._getId(node))
        
        for pid in listOfPids:
            parentContainer = self.containerNodes[pid]
            
            if len(parentContainer.itemSequences) == 0:
                # Create a new ItemSequence containing just one item
                parentContainer.itemSequences.append((itemIndex,itemIndex))
            else:
                # If the last itemSequence contains the previous item, extend it to contain the current item, too. Otherwise create a new ItemSequence containing at first only the current item.
                lastItemSequence = parentContainer.itemSequences[-1]
                if lastItemSequence[1] == itemIndex - 1:
                    # Increase the end of the sequence by 1
                    parentContainer.itemSequences[-1] = (lastItemSequence[0],itemIndex)
                elif lastItemSequence[1] < itemIndex - 1:
                    parentContainer.itemSequences.append((itemIndex,itemIndex))
                #else: In this case lastItemSequence[1] == itemIndex and this means the sequence has already been increased

            # Finally update the itemSequences of all parents of parentContainer
            self._updateItemSequences(parentContainer,itemIndex)


    def _findMaximalSequence(self,containerNodes,boundingSeq):
        """Find an item-sequence of maximal bounded length.
        
        This method finds among all item-sequences of the given ContainerNodes one that has maximal length within the interval given by <boundingSeq> (<containerNodes> is a list of ContainerNodes). It returns a tuple consisting of the maximal sequence (bounded by <boundingSeq>) and the node containing that sequence.
        
        Example: If the nodes a and b have contain item-sequences (1,7) and (5,10), respectively, and <boundingSeq> is (5,8), the result will be ((5,8),b): (1,7) bounded to the sequence (5,8) is (5,7) while (5,10) becomes (5,8) and is thus the sequence of maximal bounded length.
        
        If no sequence of positive bounded length is found, this method will return None.
        """
        maxSeq = None
        nodeWithMaxSeq = None
        
        for node in containerNodes:
            for sequence in node.itemSequences:
                # Bound the sequence by boundingSeq
                boundedSeq = (max(sequence[0],boundingSeq[0]),min(sequence[1],boundingSeq[1]))
                if boundedSeq[1] >= boundedSeq[0]: # Sequence is not empty
                    if maxSeq is None or self._seqLen(boundedSeq) > self._seqLen(maxSeq):
                        maxSeq = boundedSeq
                        nodeWithMaxSeq = node
                        
        return maxSeq,nodeWithMaxSeq
    
    
    def _findPos(self,itemIndex,itemSequences):
        """Find the position of <itemIndex> in the given list of item-sequences: If <itemIndex> is 12 and <itemSequences> is [(1,3),(5,9),(10,10),(14,16)], then return 3."""
        for i in range(0,len(itemSequences)):
            if itemIndex < itemSequences[i][0]:
                return i
        return len(itemSequences) # Behind the last item
    
    
    def _createTree(self,sequence,containerNodes):
        """Create a tree using some of the nodes in <containerNodes> as roots and covering all item from <sequence>."""
        #print("This is createTree over the sequence {0}-{1}".format(*sequence))
        coveredItems = set()
        
        roots = []
        rootSeqs = []
        
        if len(containerNodes) > 0:
            while len(coveredItems) < self._seqLen(sequence):
                maxSequence,cNode = self._findMaximalSequence(containerNodes,sequence)
                if maxSequence is None: # No sequence found: remaining items are direct children
                    break
                #print("Found a maximal sequence: {0}-{1}".format(*maxSequence))
                newNode = self._createNode(cNode.id,self._createTree(maxSequence,cNode.childContainers))
                pos = self._findPos(maxSequence[0],rootSeqs)
                roots.insert(pos,newNode)
                rootSeqs.insert(pos,maxSequence)
                coveredItems = coveredItems.union(set(self.items[maxSequence[0]:maxSequence[1]+1]))
                
                # Correct all itemSequences:
                for node in containerNodes:
                    node.itemSequences = [self._cutItemSequence(seq,maxSequence) for seq in node.itemSequences]
                    node.itemSequences = [seq for seq in node.itemSequences if seq is not None]
                
        # Add remaining items as direct children
        for itemIndex in range(sequence[0],sequence[1]+1):
            if self.items[itemIndex] not in coveredItems:
                pos = self._findPos(itemIndex,rootSeqs)
                roots.insert(pos,self.items[itemIndex])
                rootSeqs.insert(pos,(itemIndex,itemIndex))

        return roots

    def _cutItemSequence(self,a,b):
        """Cut away all parts of the sequence b from the sequence a and return the result: if b = (2,4), then a = (1,3) becomes (1,1) and a = (3,6) becomes (5,6). b must not be an inner part of a, because the result would consist of two distinct sequences (e.g. a=(1,5), b=(2,3) would result in (1,1) ∪ (4,5))."""
        if a[0]< b[0] and a[1] > b[1]:
            raise AssertionError("Sequence b is an inner part of a: {2}-{3} ⊂ {0}-{1}".format(a[0],a[1],b[0],b[1]))
        
        if a[0] < b[0]:
            return (a[0],min(a[1],b[0]-1))
        elif a[1] > b[1]:
            return (max(a[0],b[1]+1),a[1])
        else: # a is completely contained in b
            return None
        
    def _seqLen(self,sequence):
        """Return the length of an item-sequence."""
        return sequence[1] - sequence[0] + 1