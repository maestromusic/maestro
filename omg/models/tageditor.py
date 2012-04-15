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

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

from .. import constants, tags, utils, modify

translate = QtCore.QCoreApplication.translate

# If ratio of elements that have the value of a record is higher than this constant, the record is regarded
# as "usual". This is used to decide which text should be displayed: "in these x elements:" or "except in
# these x elements:".
RATIO = 0.75     
        
        
class Record:
    """The tageditor stores data not in the usual element/tags.Storage-structure but uses records consisting
    of
    
        - a tag
        - a value
        - allElements: a (reference to a) list of all elements that are currently edited by the tageditor.
          This attribute must not be changed.
        - elementsWithValue: a sublist of elements that have a tag of this value
    
    This data model resembles much more the graphical structure of the tageditor. 
    """
    def __init__(self,tag,value,allElements,elementsWithValue):
        self.tag = tag
        self.value = value
        self.allElements = allElements
        self.elementsWithValue = elementsWithValue
    
    def copy(self,copyList=False):
        """Return a copy of this record. Note that the elementsWithValue list is NOT copied by default. Set
        *copyList* to True to change this."""
        elementsWithValue = self.elementsWithValue[:] if copyList else self.elementsWithValue
        return Record(self.tag,self.value,self.allElements,elementsWithValue)
        
    def isCommon(self):
        """Return whether the value of this record is present in all elements."""
        return len(self.elementsWithValue) == len(self.allElements)
    
    def isUsual(self):
        """Return whether the value of this record is present in "a great part" of the elements. The precise
        meaning of "a great part" depends on the constant RATIO."""
        return len(self.elementsWithValue) >= RATIO * len(self.allElements)
    
    def getExceptions(self):
        """Return a list of elements that do not have the value of this record."""
        return [element for element in self.allElements if element not in self.elementsWithValue]
    
    def append(self,element):
        """Append an element to this record. Call this after adding the value of this record to *element*.
        Return whether the element was not already contained in ''elementsWithValue''."""
        if element not in self.elementsWithValue:
            self.elementsWithValue.append(element)
            return True
        return False
    
    def extend(self,elements):
        """Append several elements to this record. Call this after adding the value of this record to
        *elements*. Return True if any element was not already contained in ''elementsWithValue''."""
        # Take care that self.append is executed for all elements
        results = [self.append(element) for element in elements]
        return any(results)
            
    def removeElements(self,elements):
        """Remove some elements from this record. Call this after removing the value of this record from
        *elements*."""
        for element in elements:
            self.elementsWithValue.remove(element)
            
    def __str__(self):
        if self.isCommon():
            return str(self.value)
        elif len(self.elementsWithValue) == 1:
            return translate("TagEditor","{} in {}").format(self.value,self.elementsWithValue[0])
        elif len(self.getExceptions()) == 1:
            return translate("TagEditor","{} except in {}").format(self.value,self.getExceptions()[0])
        else: return translate("TagEditor","{} in {} pieces").format(self.value,len(self.elementsWithValue))


class TagEditorUndoCommand(QtGui.QUndoCommand):
    def __init__(self,model,text):
        super().__init__(text)
        self.model = model
        self.redoMethods = []
        self.undoMethods = []
        self.ids = []
        self._elementListNumber = model._elementListNumber
        self._finished = False

    def addMethod(self,method,*params):
        assert not self._finished
        recordModel = self.model.records
        self.redoMethods.append((method,params))

        # Compute corresponding undo-method and params
        # Furthermore update the list of changed ids
        if method.__name__ == 'insertRecord':
            pos,record = params
            undoMethod = recordModel.removeRecord
            undoParams = (record,)
            self._updateIds(record)
        elif method.__name__ == 'removeRecord':
            record = params[0] # 'record, = params' would work, too.
            pos = recordModel[record.tag].index(record)
            undoMethod = recordModel.insertRecord
            undoParams = (pos,record)
            self._updateIds(record)
        elif method.__name__ == 'changeRecord':
            tag,oldRecord,newRecord = params
            undoMethod = recordModel.changeRecord
            undoParams = (tag,newRecord,oldRecord)
            self._updateIds(oldRecord)
            self._updateIds(newRecord)
        elif method.__name__ == 'moveRecord':
            tag,oldPos,newPos = params
            undoMethod = recordModel.moveRecord
            undoParams = (tag,newPos,oldPos)
        elif method.__name__ == 'insertTag':
            pos,tag = params
            undoMethod = recordModel.removeTag
            undoParams = (tag,)
        elif method.__name__ == 'removeTag':
            tag = params[0]
            pos = recordModel.tags().index(tag)
            undoMethod = recordModel.insertTag
            undoParams = (pos,tag)
        elif method.__name__ == 'changeTag':
            oldTag,newTag = params
            undoMethod = recordModel.changeTag
            undoParams = (newTag,oldTag)
        self.undoMethods.append((undoMethod,undoParams))
        
        method(*params)
        self.modifyLevel(method,params)

    def _updateIds(self,record):
        self.ids.extend(element.id for element in record.elementsWithValue if element.id not in self.ids)

    def finish(self):
        self.model.level.emitEvent(self.ids)
        self._finished = True
        
    def redo(self):
        if len(self.redoMethods):
            for method,params in self.redoMethods:
                if self._elementListNumber == self.model._elementListNumber:
                    method(*params)
                self.modifyLevel(method,params)
            self.model.level.emitEvent(self.ids)

    def undo(self):
        if len(self.undoMethods):
            for method,params in reversed(self.undoMethods):
                if self._elementListNumber == self.model._elementListNumber:
                    method(*params)
                self.modifyLevel(method,params)
            self.model.level.emitEvent(self.ids)

    def modifyLevel(self,method,params):
        if method.__name__ == 'insertRecord':
            pos,record = params
            self.model.level.addTagValue(record.tag,record.value,record.elementsWithValue,emitEvent=False)
        elif method.__name__ == 'removeRecord':
            record = params[0] # 'record, = params' would work, too.
            self.model.level.removeTagValue(record.tag,record.value,record.elementsWithValue,emitEvent=False)
        elif method.__name__ == 'changeRecord':
            tag,oldRecord,newRecord = params
            
            if oldRecord.tag != newRecord.tag:
                self.model.level.removeTagValue(oldRecord.tag,oldRecord.value,
                                                oldRecord.elementsWithValue,emitEvent=False)
                self.model.level.addTagValue(newRecord.tag,newRecord.value,
                                             newRecord.elementsWithValue,emitEvent=False)
            else:
                oldElements = set(oldRecord.elementsWithValue)
                newElements = set(newRecord.elementsWithValue)
                removeList = list(oldElements - newElements)
                addList = list(newElements - oldElements)
                if len(removeList):
                    self.model.level.removeTagValue(oldRecord.tag,oldRecord.value,removeList,emitEvent=False)
                if len(addList):
                    self.model.level.addTagValue(newRecord.tag,newRecord.value,addList,emitEvent=False)
                    
                if oldRecord.value != newRecord.value:
                    changeList = list(newElements.intersection(oldElements))
                    if len(changeList):
                        self.model.level.changeTagValue(tag,oldRecord.value,newRecord.value,
                                                        changeList,emitEvent=False)
    
    
class RecordModel(QtCore.QObject):
    # the inner model is basically the datastructure used by the tageditor
    #TODO: rewrite
    """The inner model of the tag editor. It stores the actual data in an OrderedDict mapping tags to list
    of records (similar to the tageditor's GUI). It provides a set of basic commands to change the data and
    will emit signals when doing so. Intentionally the commands of InnerModel are very basic, so that each
    command can be undone easily. In contrast to the TagEditorModel the inner model does not do any
    Undo/Redo-stuff. Instead, TagEditorModel splits its complicated actions into several calls of the methods
    of InnerModel, puts each of these calls into an UndoCommand and pushes these commands as one macro on the
    stack.
    
    An effect of this design is that InnerModel may have states that would be inconsistent for TagEditorModel
    (e.g. a tag with empty record list, or records with tag A in ''self.tags[tag B]'').
    
    Another advantage of having only basic commands is that the GUI has only to react to basic signals.
    """
    tagInserted = QtCore.pyqtSignal(int,tags.Tag)
    tagRemoved = QtCore.pyqtSignal(tags.Tag)
    tagChanged = QtCore.pyqtSignal(tags.Tag,tags.Tag)
    recordInserted = QtCore.pyqtSignal(int,Record)
    recordRemoved = QtCore.pyqtSignal(Record)
    recordChanged = QtCore.pyqtSignal(tags.Tag,Record,Record)
    recordMoved = QtCore.pyqtSignal(tags.Tag,int,int)
    
    # This signal is emitted, when the number of common records of a tag has changed
    commonChanged = QtCore.pyqtSignal(tags.Tag)

    def __getitem__(self,key):
        return self._records[key]

    def __setitem__(self,key,value):
        self._records[key] = value

    def __delitem__(self,key):
        del self._records[key]

    def keys(self):
        return self._records.keys()

    def values(self):
        return self._records.values()

    def items(self):
        return self._records.items()

    def tags(self):
        return list(self._records.keys())
        
    def setRecords(self,records):
        self._records = utils.OrderedDict()
        for record in records:
            if record.tag not in self._records:
                self._records[record.tag] = [record]
            else: self._records[record.tag].append(record)
    
    def get(self,tag,value):
        """Return the record with the given tag and value from the model if such a record exists or None
        otherwise."""
        if tag in self._records:
            for record in self._records[tag]:
                if record.value == value:
                    return record
        return None

    def insertRecord(self,pos,record):
        """Insert *record* at position *pos* into the list of records with tag ''record.tag''. This list must
        exist before you call this method, so you may need to call addTag first."""
        self._records[record.tag].insert(pos,record)
        self.recordInserted.emit(pos,record)
        if record.isCommon():
            self.commonChanged.emit(record.tag)

    def removeRecord(self,record):
        """Remove a record from the model."""
        pos = self._records[record.tag].index(record)
        del self._records[record.tag][pos]
        self.recordRemoved.emit(record)
        if record.isCommon():
            self.commonChanged.emit(record.tag)
            
    def changeRecord(self,tag,oldRecord,newRecord):
        """Replace the record *oldRecord* by *newRecord*. The replacement will take place in the list of
        records with tag *tag*, regardless of the tags stored in the records (those tags may differ)."""
        pos = self._records[tag].index(oldRecord)
        self._records[tag][pos] = newRecord
        self.recordChanged.emit(tag,oldRecord,newRecord)
        if oldRecord.isCommon() != newRecord.isCommon():
            self.commonChanged.emit(tag)

    def moveRecord(self,tag,oldPos,newPos):
        """Within the list of records of tag *tag* move a record from position *oldPos* to position
        *newPos*."""
        if oldPos != newPos:
            self._records[tag].insert(newPos,self._records[tag][oldPos])
            if oldPos < newPos:
                del self._records[tag][oldPos]
            else: del self._records[tag][oldPos + 1]
            self.recordMoved.emit(tag,oldPos,newPos)
            
    def insertTag(self,pos,tag):
        """Insert the given tag at position *pos* into the OrderedDict. The list of records will be empty."""
        self._records.insert(pos,tag,[])
        self.tagInserted.emit(pos,tag)

    def removeTag(self,tag):
        """Remove the given tag from the model. The list of records with this tag must be empty before this
        method may be called."""
        assert len(self._records[tag]) == 0
        del self._records[tag]
        self.tagRemoved.emit(tag)

    def changeTag(self,oldTag,newTag):
        """Change the tag *oldTag* into *newTag*. This method won't touch any records, so you may have to
        change the tags in the records by calling changeRecord. *newTag* must not already be contained in
        the model."""
        self._records.changeKey(oldTag,newTag)
        self.tagChanged.emit(oldTag,newTag)


class TagEditorModel(QtCore.QObject):
    """The model of the tageditor. It stores
    
        - a list of elements that are currently edited.
        - a dict mapping tags to records of the tags. Each records stores a value and the sublist of
          elements having this tag-value pair.
    
    Due to this different data structure, TagEditorModel will delete the tags in its copy of *elements* after
    creating the records. Besides fewer memory consumption the main reason for deleting the tags is that we
    want to update only one structure on ChangeEvents. In fact if saveDirectly is false, a backup of the tags
    is kept in element.originalTags and used in the UndoCommand.
    
    Now the tageditor clearly needs some title to display for each element, so we store the (concatenated)
    title in element.title and update it when necessary.
    """
    resetted = QtCore.pyqtSignal()
    
    def __init__(self,level,elements,stack=None):
        QtCore.QObject.__init__(self)
        
        self.level = level
        self._elementListNumber = 0
        
        self.records = RecordModel()
        self.tagInserted = self.records.tagInserted
        self.tagRemoved = self.records.tagRemoved
        self.tagChanged = self.records.tagChanged
        self.recordInserted = self.records.recordInserted
        self.recordRemoved = self.records.recordRemoved
        self.recordChanged = self.records.recordChanged
        self.recordMoved = self.records.recordMoved
        self.commonChanged = self.records.commonChanged
            
        self.setElements(elements)
        
        if stack is None:
            self.stack = modify.stack
        else: self.stack = stack

    def getTags(self):
        """Return the list of tags that are present in any of the elements currently edited."""
        return list(self.records.keys())

    def getRecords(self,tag):
        """Return the list of records with the given tag."""
        return self.records[tag]

    def getElements(self):
        """Return a list of all elements currently edited."""
        return self.elements
    
    def setElements(self,elements):
        """Set the list of edited elements and reset the tageditor."""
        self._elementListNumber += 1
        self.elements = elements
        self.createRecords()

    def createRecords(self):
        """Create the internal data structure from the given list of elements."""
        records = {}
        for element in self.elements:
            for tag in element.tags:
                for value in element.tags[tag]:
                    if (tag,value) in records:
                        records[(tag,value)].elementsWithValue.append(element)
                    else: records[(tag,value)] = Record(tag,value,self.elements,[element])
        self.records.setRecords(records.values())
        self.resetted.emit()

    def addRecord(self,record):
        """Add a record to the model. If there is already a record with same tag and value the elements
        with that value will be merged from both records."""
        command = TagEditorUndoCommand(self,self.tr("Add record"))
        self.stack.push(command)
        result = self._insertRecord(command,None,record)
        command.finish()
        return result

    def _insertRecord(self,command,pos,record):
        """Insert a record at the position *pos*. This is a helper function used by e.g. addRecord. It does
        not start a new macro and should therefore not be used from outside this class."""
        #TODO: return value?
        if record.tag not in self.records.tags():
            # Add the missing tag
            command.addMethod(self.records.insertTag,len(self.records.tags()),record.tag)

        # Does there already exist a record with the same tag and value?
        existingRecord = self.records.get(record.tag,record.value)
        if existingRecord is None:
            # Simply add the record
            if pos is None:
                if record.isCommon():
                    pos = self._commonCount(record.tag)
                else: pos = len(self.records[record.tag])
            else: assert pos <= len(self.records[record.tag])
            command.addMethod(self.records.insertRecord,pos,record)
            return True
        else:
            # Now things get complicated: Add the record's elements to those of (a copy of)
            # the existing record.
            copy = existingRecord.copy(True)
            if copy.extend(record.elementsWithValue):
                command.addMethod(self.records.changeRecord,record.tag,existingRecord,copy)
                # If this makes the record common, move it to the right place
                if existingRecord.isCommon() != copy.isCommon():
                    self._checkCommonAndMove(command,copy)
            return False
            
    def removeRecord(self,record):
        """Remove a record from the model."""
        command = TagEditorUndoCommand(self,self.tr("Remove record"))
        self.stack.push(command)
        self._removeRecord(command,record)
        command.finish()

    def _removeRecord(self,command,record):
        command.addMethod(self.records.removeRecord,record)
        if len(self.records[record.tag]) == 0:
            # Remove the empty tag
            command.addMethod(self.records.removeTag,record.tag)
        
    def removeRecords(self,records):
        """Remove several records from the model."""
        if len(records) > 0:
            command = TagEditorUndoCommand(self,self.tr("Remove record(s)",'',len(records)))
            self.stack.push(command)
            for record in records:
                self._removeRecord(command,record)
            command.finish()

    def changeRecord(self,oldRecord,newRecord):
        """Change the record *oldRecord* into *newRecord*. This method will handle all complicated stuff that
        can happen (e.g. when oldRecord.tag != newRecord.tag or when a record with the same tag and value as
        *newReword* does already exist).
        """
        command = TagEditorUndoCommand(self,self.tr("Change record"))
        self.stack.push(command)

        # If the tag has changed or the new value does already exist, we simply remove the old and add the
        # new record. Otherwise we really change the record so that its position stays the same because this
        # is what the user expects.
        if oldRecord.tag != newRecord.tag or self.records.get(newRecord.tag,newRecord.value) is not None:
            self._removeRecord(command,oldRecord)
            self._insertRecord(command,len(self.records[newRecord.tag]),newRecord)
        else: 
            command.addMethod(self.records.changeRecord,oldRecord.tag,oldRecord,newRecord)
            self._checkCommonAndMove(command,newRecord)
        command.finish()

    def removeTag(self,tag):
        """Remove all records with tag *tag*."""
        command = TagEditorUndoCommand(self,self.tr("Remove tag"))
        self.stack.push(command)
        # First remove all records
        while len(self.records[tag]) > 0:
            command.addMethod(self.records.removeRecord,self.records[tag][0])
        # Remove the empty tag
        command.addMethod(self.records.removeTag,record.tag)
        command.finish()

    def changeTag(self,oldTag,newTag):
        """Change tag *oldTag* into *newTag*. This will convert the values and tags of the affected records
        and handle special cases (e.g. when one of the values is already present in *newTag*).
        If the conversion of any of the values fails, this method will do nothing and return False. After a
        successful change it will return true.
        """
        # First check whether the existing values in oldTag are convertible to newTag
        try:
            for record in self.records[oldTag]:
                # Do nothing with the return value, we only check whether conversion is possible
                oldTag.type.convertValue(newTag.type,record.value)
        except ValueError:
            return False # conversion not possible
        command = TagEditorUndoCommand(self,self.tr("Change tag"))
        self.stack.push(command)

        if newTag not in self.records.tags():
            # First change the tag itself. This is necessary so that the tageditor can react to the
            # recordChanged-signals below.
            command.addMethod(self.records.changeTag,oldTag,newTag)
            # Then change all records:
            for record in self.records[newTag]:
                newRecord = record.copy()
                newRecord.tag = newTag
                newRecord.value = oldTag.type.convertValue(newTag.type,record.value)
                command.addMethod(self.records.changeRecord,newTag,record,newRecord)
        else: # Now we have to add all converted records to the existing tag
            # The easiest way to do this is to remove all records and add the converted records again
            for record in self.records[oldTag]:
                newRecord = record.copy()
                newRecord.tag = newTag
                newRecord.value = oldTag.type.convertValue(newTag.type,record.value)
                self._insertRecord(command,None,newRecord)
                command.addMethod(self.records.removeRecord,record)
            # Finally remove the old tag
            command.addMethod(self.records.removeTag,oldTag)

        command.finish()
        return True

    def getTagsOfElement(self,element):
        """Return the tags of the given element as stored in the records."""
        result = tags.Storage()
        for tag,records in self.records.items():
            for record in records:
                if element in record.elementsWithValue:
                    result.add(tag,record.value)
        return result
        
    def _checkCommonAndMove(self,command,record):
        #TODO: comment
        """Check whether *record* is at a valid position (uncommon records come after common ones) and if
        not move it to a valid position. If *undoable* is True this move operation will be undoable.
        *undoable* should be True if the change in common-state was triggered directly by the user in this
        tageditor and False if it happened while the tageditor reacted to an event.
        """
        pos = self.records[record.tag].index(record)
        border = self._commonCount(record.tag)
        if (record.isCommon() and pos < border) or (not record.isCommon() and pos >= border):
            return # nothing to do
        newPos = border - 1 if record.isCommon() else border
        command.addMethod(self.records.moveRecord,record.tag,pos,newPos)
                
    def _addElementsWithValue(self,tag,value,elements):
        """Add *elements* to the record defined by *tag* and *value*. Create the record when necessary."""
        if len(elements) == 0:
            return
        record = self.inner.getRecord(tag,value)
        if record is None:
            if tag not in self.inner.tags:
                self.inner.insertTag(len(self.inner.tags),tag)
            record = Record(tag,value,self.inner.elements,elements)
            pos = self._commonCount(tag) if record.isCommon() else len(self.inner.tags[tag])
            self.inner.insertRecord(pos,record)
        else:
            newElementsWithValue = [el for el in self.inner.elements if el in record.elementsWithValue
                                                                         or el in elements]
            if len(newElementsWithValue) > len(record.elementsWithValue):
                newRecord = record.copy()
                newRecord.elementsWithValue = newElementsWithValue
                self.inner.changeRecord(record.tag,record,newRecord)
                if newRecord.isCommon() and not record.isCommon():
                    self._checkCommonAndMove(record,undoable=False)
                    self.commonChanged.emit(record.tag)

    def _removeElementsWithValue(self,tag,value,elements):
        """Remove *elements* from the record defined by *tag* and *value*. Delete the record if it is
        empty afterwards."""
        if len(elements) == 0:
            return
        record = self.inner.getRecord(tag,value)
        if record is not None: # otherwise there is nothing to do
            remaining = [el for el in record.elementsWithValue if el not in elements]
            if len(remaining) == 0:
                self.inner.removeRecord(record)
            elif len(remaining) < len(record.elementsWithValue):
                newRecord = record.copy()
                newRecord.elementsWithValue = remaining
                self.inner.changeRecord(record.tag,record,newRecord)
                if record.isCommon():
                    self._checkCommonAndMove(record,undoable=False)
                    self.commonChanged.emit(record.tag)
        
    def getPossibleSeparators(self,records):
        """Return all separators (from constants.SEPARATORS) that are present in every value of the given
        records."""
        # Collect all separators appearing in the first record
        if len(records) == 0 or any(record.tag.type == tags.TYPE_DATE for record in records):
            return []
        result = [s for s in constants.SEPARATORS if s in records[0].value]
        for record in records[1:]:
            if len(result) == 0:
                break
            # Filter those that do not appear in the other records
            result = list(filter(lambda s: s in record.value,result))
        return result
        
    
    def split(self,record,separator):
        """Split the given record using the separator *separator*. If ''record.value'' is for example
        ''Artist 1/Artist 2'' and ''separator=='/''', this method will change the value of record to
        ''Artist 1'' and insert a new record with value ''Artist 2'' after it.
        
        This method will return true if the split was successful.
        """
        command = TagEditorUndoCommand(self,self.tr("Split"))
        self.stack.push(command)
        result = self._split(command,record,separator)
        command.finish()
        return result
    
    def splitMany(self,records,separator):
        """Split each of the given records using *separator*. Return true if all splits were successful."""
        command = TagEditorUndoCommand(self,self.tr("Split many"))
        self.stack.push(command)
        result = any(self._split(command,record,separator) for record in records)
        command.finish()
        return result
    
    def _split(self,command,record,separator):
        #TODO comment
        splittedValues = record.value.split(separator)
        if len(splittedValues) == 0:
            return True # Nothing to split...thus the split was successful :-)
        if not all(record.tag.isValid(value) for value in splittedValues):
            return False
            
        pos = self.records[record.tag].index(record)
        
        # First remove the old value
        command.addMethod(self.records.removeRecord,record)
        
        # Now create new records and insert them at pos
        for value in splittedValues:
            newRecord = record.copy()
            newRecord.value = value
            # This is false if the record was added to an already existing one
            if self._insertRecord(command,pos,newRecord):
                pos = pos + 1
                
        return True

    def editMany(self,records,newValues):
        """Given a list of records and an equally long list of values change the value of the i-th record to
        the i-th value."""
        command = TagEditorUndoCommand(self,self.tr("Edit many"))
        self.stack.push(command)
        for record, value in zip(records,newValues):
            newRecord = record.copy()
            newRecord.value = value
            command.addMethod(self.records.changeRecord,record.tag,record,newRecord)

    def extendRecords(self,records):
        """Make the given records common, i.e. set ''record.elementsWithValue'' to all elements."""
        command = TagEditorUndoCommand(self,self.tr("Extend records"))
        self.stack.push(command)

        for record in records:
            if record.isCommon():
                continue
            
            # Maybe we have to change the record's position, since it is common afterwards
            pos = self.records[record.tag].index(record)
            newPos = self._commonCount(record.tag)
            
            newRecord = record.copy()
            newRecord.elementsWithValue = self.elements[:] # copy the list!
            command.addMethod(self.records.changeRecord,record.tag,record,newRecord)
            
            if pos != newPos:
                command.addMethod(self.records.moveRecords,records.tag,pos,newPos)

    def _commonCount(self,tag):
        """Return the number of records of the given tag that are common (i.e. all elements have the
        record's value)."""
        return sum(record.isCommon() for record in self.records[tag])
