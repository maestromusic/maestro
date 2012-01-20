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
from ..constants import REAL, EDITOR

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
        """Append a element to this record. Call this after adding the value of this record to *element*.
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


class InnerModel(QtCore.QObject):
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

    def createRecords(self):
        """Create the internal data structure from the list of elements stored in this model."""
        self.tags = utils.OrderedDict()
        for element in self.elements:
            for tag in element.tags:
                if not tag in self.tags:
                    self.tags[tag] = []
                recordList = self.tags[tag]
                for value in element.tags[tag]:
                    record = self.getRecord(tag,value)
                    if record is None:
                        # Create a new record
                        recordList.append(Record(tag,value,self.elements,[element]))
                    else: record.append(element)
    
    def getRecord(self,tag,value):
        """Return the record with the given tag and value from the model if such a record exists or None
        otherwise."""
        if tag in self.tags:
            for record in self.tags[tag]:
                if record.value == value:
                    return record
        return None

    def insertRecord(self,pos,record):
        """Insert *record* at position *pos* into the list of records with tag ''record.tag''. This list must
        exist before you call this method, so you may need to call addTag first."""
        self.tags[record.tag].insert(pos,record)
        self.recordInserted.emit(pos,record)

    def removeRecord(self,record):
        """Remove a record from the model."""
        pos = self.tags[record.tag].index(record)
        del self.tags[record.tag][pos]
        self.recordRemoved.emit(record)
            
    def changeRecord(self,tag,oldRecord,newRecord):
        """Replace the record *oldRecord* by *newRecord*. The replacement will take place in the list of
        records with tag *tag*, regardless of the tags stored in the records (those tags may differ)."""
        pos = self.tags[tag].index(oldRecord)
        self.tags[tag][pos] = newRecord
        self.recordChanged.emit(tag,oldRecord,newRecord)

    def moveRecord(self,tag,oldPos,newPos):
        """Within the list of records of tag *tag* move a record from position *oldPos* to position
        *newPos*."""
        if oldPos != newPos:
            self.tags[tag].insert(newPos,self.tags[tag][oldPos])
            if oldPos < newPos:
                del self.tags[tag][oldPos]
            else: del self.tags[tag][oldPos + 1]
            self.recordMoved.emit(tag,oldPos,newPos)
            
    def insertTag(self,pos,tag):
        """Insert the given tag at position *pos* into the OrderedDict. The list of records will be empty."""
        self.tags.insert(pos,tag,[])
        self.tagInserted.emit(pos,tag)

    def removeTag(self,tag):
        """Remove the given tag from the model. The list of records with this tag must be empty before this
        method may be called."""
        assert len(self.tags[tag]) == 0
        del self.tags[tag]
        self.tagRemoved.emit(tag)

    def changeTag(self,oldTag,newTag):
        """Change the tag *oldTag* into *newTag*. This method won't touch any records, so you may have to
        change the tags in the records by calling changeRecord. *newTag* must not already be contained in
        the model."""
        self.tags.changeKey(oldTag,newTag)
        self.tagChanged.emit(oldTag,newTag)


class UndoCommand(QtGui.QUndoCommand):
    """UndoCommand used by the tageditor. It stores one of the methods of InnerModel and some arguments. On
    redo this method will be called with the arguments. When creating the command it will calculate the
    inverse method of InnerModel and the necessary arguments and on undo that method is called.
    
    If the model saves its changes directly to the database or the editor (i.e. the tageditor is not running
    as a dialog) redo and undo will not only change the inner model but also call the correct modify-methods
    (on REAL-level) or emit the correct events (on EDITOR-level).
    
    Constructor parameters:
    
        - *model*: the tageditormodel (not the inner model!)
        - *method*: one of the methods of the inner model
        - *params*: arguments to be passed to *method*
        - text: a text for the UndoCommand (confer QtGui.QUndoCommand).
        
    \ """
    def __init__(self,model,method,*params,text=None):
        QtGui.QUndoCommand.__init__(self,text)
        self.model = model
        self.method = method
        self.params = params
        self.level = model.level
        if method.__name__ == 'insertRecord':
            pos,record = params
            self.undoMethod = model.inner.removeRecord
            self.undoParams = [record]
        elif method.__name__ == 'removeRecord':
            record = params[0] # 'record, = params' would work, too.
            pos = model.inner.tags[record.tag].index(record)
            self.undoMethod = model.inner.insertRecord
            self.undoParams = [pos,record]
        elif method.__name__ == 'changeRecord':
            tag,oldRecord,newRecord = params
            self.undoMethod = model.inner.changeRecord
            self.undoParams = [tag,newRecord,oldRecord]
        elif method.__name__ == 'moveRecord':
            tag,oldPos,newPos = params
            self.undoMethod = model.inner.moveRecord
            self.undoParams = [tag,newPos,oldPos]
        elif method.__name__ == 'insertTag':
            pos,tag = params
            self.undoMethod = model.inner.removeTag
            self.undoParams = [tag]
        elif method.__name__ == 'removeTag':
            tag = params[0]
            pos = model.inner.tags.index(tag)
            self.undoMethod = model.inner.insertTag
            self.undoParams = [pos,tag]
        elif method.__name__ == 'changeTag':
            oldTag,newTag = params
            self.undoMethod = model.inner.changeTag
            self.undoParams = [newTag,oldTag]

    def _modify(self,redo):
        """Redo this command or undo it, depending on the parameter *redo*."""
        if self.method.__name__ == 'insertRecord':
            pos,record = self.params
            self._execute('add' if redo else 'remove',record.elementsWithValue,record.tag,record.value)
        elif self.method.__name__ == 'removeRecord':
            record = self.params[0] # 'record, = self.params' would work, too.
            self._execute('remove' if redo else 'add',record.elementsWithValue,record.tag,record.value)
        elif self.method.__name__ == 'changeRecord':
            if redo:
                tag,oldRecord,newRecord = self.params
            else: tag,newRecord,oldRecord = self.params
        
            if oldRecord.tag != newRecord.tag:
                self._execute('remove',oldRecord.elementsWithValue,oldRecord.tag,oldRecord.value)
                self._execute('add',newRecord.elementsWithValue,newRecord.tag,newRecord.value)
            else:
                oldElements = set(oldRecord.elementsWithValue)
                newElements = set(newRecord.elementsWithValue)
                removeList = list(oldElements - newElements)
                addList = list(newElements - oldElements)
                if len(removeList):
                    self._execute('remove',removeList,oldRecord.tag,oldRecord.value)
                if len(addList):
                    self._execute('add',addList,newRecord.tag,newRecord.value)
                    
                if oldRecord.value != newRecord.value:
                    changeList = list(newElements.intersection(oldElements))
                    if len(changeList):
                        self._execute('change',changeList,oldRecord.tag,oldRecord.value,newRecord.value)
        
    def redo(self):
        #print("REDO: {} [{}]".format(self.method.__name__,", ".join(str(p) for p in self.params)))
        # First modify the inner model
        self.method(*self.params)
        # Then modify the editor or the database
        if self.model.saveDirectly:
            self._modify(True)
            
    def undo(self):
        # First modify the inner model
        self.undoMethod(*self.undoParams)
        # Then modify the editor or the database
        if self.model.saveDirectly:
            self._modify(False)

    def _execute(self,type,elements,*params):
        """Depending on the level either emit a SingleTagChangeEvent (EDITOR) or call a function from
        modify.real (REAL), which will emit an event after really changing things. *type* is one of 'add',
        'remove' or 'change' and determines which event or function should be used. *elements* are the
        affected elements (one of the arguments of the event/function) and *params* are the other parameters
        (corresponding event/function pairs share the same signature).
        """
        if self.model.level == EDITOR:
            ids = [element.id for element in elements]
            theClass = {
                'add': modify.events.TagValueAddedEvent,
                'remove': modify.events.TagValueRemovedEvent,
                'change': modify.events.TagValueChangedEvent
            }[type]
            modify.dispatcher.changes.emit(theClass(EDITOR,elementIDs=ids,*params))
        else:
            theFunction = {
                'add': modify.real.addTagValue,
                'remove': modify.real.removeTagValue,
                'change': modify.real.changeTagValue
            }[type]
            theFunction(elements=elements,*params)


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
    commonChanged = QtCore.pyqtSignal(tags.Tag)
    titlesChanged = QtCore.pyqtSignal(list)
    
    def __init__(self,level,elements,saveDirectly):
        QtCore.QObject.__init__(self)
        
        self.level = level
        self.saveDirectly = saveDirectly
        
        self.inner = InnerModel()
        self.tagInserted = self.inner.tagInserted
        self.tagRemoved = self.inner.tagRemoved
        self.tagChanged = self.inner.tagChanged
        self.recordInserted = self.inner.recordInserted
        self.recordRemoved = self.inner.recordRemoved
        self.recordChanged = self.inner.recordChanged
        self.recordMoved = self.inner.recordMoved
    
        if not saveDirectly:
            self.undoStack = QtGui.QUndoStack(self)
            
        self.setElements(elements)
        
        # This may be deactivated if the FlagEditor is run as a dialog...but it should not cause any harm.
        modify.dispatcher.changes.connect(self._handleDispatcher)

    def getTags(self):
        """Return the list of tags that are present in any of the elements currently edited."""
        return list(self.inner.tags.keys())

    def getRecords(self,tag):
        """Return the list of records with the given tag."""
        return self.inner.tags[tag]

    def getElements(self):
        """Return a list of all elements currently edited."""
        return self.inner.elements
    
    def setElements(self,elements):
        """Set the list of edited elements and reset the tageditor."""
        # Do not copy the tags as they will be deleted (unless saveDirectly is false)
        self.inner.elements = [el.export(attributes=['tags','path']) for el in elements]
        if not self.saveDirectly: # In this case we have to copy
            for element in self.inner.elements:
                element.originalTags = element.tags
        self.createRecords()
    
    def createRecords(self):
        self.inner.createRecords()
        for element in self.inner.elements:
            # Store the title because the tags will be removed
            element.title = element.getTitle()
            del element.tags
        self.resetted.emit()
        
    def reset(self):
        """Reset the tageditor."""
        self.inner.createRecords()
        if not self.saveDirectly:
            self.undoStack.clear()
        self.resetted.emit()

    def createRedoAction(self,parent=None,prefix=""):
        """Create an action redoing the last change in this model."""
        if self.saveDirectly:
            return modify.createRedoAction(parent,prefix)
        else: return self.undoStack.createRedoAction(parent,prefix)
    
    def createUndoAction(self,parent=None,prefix=""):
        """Create an action undoing the last change in this model."""
        if self.saveDirectly:
            return modify.createUndoAction(parent,prefix)
        else: return self.undoStack.createUndoAction(parent,prefix)
        
    def _beginMacro(self,name):
        """Start a macro with the given name on the correct UndoStack."""
        if self.saveDirectly:
            modify.beginMacro(self.level,name)
        else: self.undoStack.beginMacro(name)
    
    def _push(self,command):
        """Push the UndoCommand *command* to the correct UndoStack."""
        if self.saveDirectly:
            modify.push(command)
        else: self.undoStack.push(command)
        
    def _endMacro(self):
        """End a macro on the correct UndoStack."""
        if self.saveDirectly:
            modify.endMacro()
        else: self.undoStack.endMacro()
        
    def addRecord(self,record):
        """Add a record to the model. If there is already a record with same tag and value the elements
        with that value will be merged from both records.""" 
        self._beginMacro(self.tr("Add Record"))
        result = self._insertRecord(None,record)
        self._endMacro()
        return result

    def _insertRecord(self,pos,record):
        """Insert a record at the position *pos*. This is a helper function used by e.g. addRecord. It does
        not start a new macro and should therefore not be used from outside this class."""
        if record.tag not in self.inner.tags:
            # Add the missing tag
            command = UndoCommand(self,self.inner.insertTag,len(self.inner.tags),record.tag)
            self._push(command)

        # Does there already exist a record with the same tag and value?
        existingRecord = self.inner.getRecord(record.tag,record.value)
        if existingRecord is None:
            # Simply add the record
            if pos is None:
                if record.isCommon():
                    pos = self._commonCount(record.tag)
                else: pos = len(self.inner.tags[record.tag])
            else: assert pos <= len(self.inner.tags[record.tag])
            command = UndoCommand(self,self.inner.insertRecord,pos,record)
            self._push(command)
            return True
        else:
            # Now things get complicated: Add the record's elements to those of (a copy of)
            # the existing record.
            copy = existingRecord.copy(True)
            copy.extend(record.elementsWithValue)
            command = UndoCommand(self,self.inner.changeRecord,record.tag,existingRecord,copy)
            self._push(command)
            if existingRecord.isCommon() != copy.isCommon():
                self._checkCommonAndMove(copy,undoable=True)
                self.commonChanged.emit(record.tag)
            return False
            
    def removeRecord(self,record):
        """Remove a record from the model."""
        self._beginMacro(self.tr("Remove record"))
        command = UndoCommand(self,self.inner.removeRecord,record)
        self._push(command)
        if len(self.inner.tags[record.tag]) == 0:
            # Remove the empty tag
            command = UndoCommand(self,self.inner.removeTag,record.tag)
            self._push(command)
        self._endMacro()

    def removeRecords(self,records):
        """Remove several records from the model."""
        if len(records) > 0:
            self._beginMacro(self.tr("Remove record(s)",'',len(records)))
            for record in records:
                self.removeRecord(record)
            self._endMacro()

    def changeRecord(self,oldRecord,newRecord):
        """Change the record *oldRecord* into *newRecord*. This method will handle all complicated stuff that
        can happen (e.g. when oldRecord.tag != newRecord.tag or when a record with the same tag and value as
        *newReword* does already exist).
        """
        self._beginMacro(self.tr("Change record"))

        # If the tag has changed or the new value does already exist, we simply remove the old and add the
        # new record. Otherwise we really change the record so that its position stays the same because this
        # is what the user expects.
        if oldRecord.tag != newRecord.tag or self.inner.getRecord(newRecord.tag,newRecord.value) is not None:
            self.removeRecord(oldRecord)
            self.addRecord(newRecord)
        else:
            command = UndoCommand(self,self.inner.changeRecord,oldRecord.tag,oldRecord,newRecord)
            self._push(command)
        self._endMacro()

    def removeTag(self,tag):
        """Remove all records with tag *tag*."""
        self._beginMacro(self.tr("Remove tag"))
        # First remove all records
        while len(self.inner.tags[tag]) > 0:
            record = self.inner.tags[tag][0]
            command = UndoCommand(self,self.inner.removeRecord,record)
            self._push(command)
        # Remove the empty tag
        command = UndoCommand(self,self.inner.removeTag,record.tag)
        self._push(command)
        self._endMacro()

    def changeTag(self,oldTag,newTag):
        """Change tag *oldTag* into *newTag*. This will convert the values and tags of the affected records
        and handle special cases (e.g. when one of the values is already present in *newTag*).
        If the conversion of any of the values fails, this method will do nothing and return False. After a
        successful change it will return true.
        """
        # First check whether the existing values in oldTag are convertible to newTag
        try:
            for record in self.inner.tags[oldTag]:
                oldTag.type.convertValue(newTag.type,record.value)
        except ValueError:
            return False # conversion not possible
        self._beginMacro(self.tr("Change Tag"))

        if newTag not in self.inner.tags:
            # First change the tag itself. This is necessary so that the tageditor can react to the
            # recordChanged-signals below.
            command = UndoCommand(self,self.inner.changeTag,oldTag,newTag)
            self._push(command)
            # Then change all records:
            for record in self.inner.tags[newTag]:
                newRecord = record.copy()
                newRecord.tag = newTag
                newRecord.value = oldTag.type.convertValue(newTag.type,record.value)
                command = UndoCommand(self,self.inner.changeRecord,newTag,record,newRecord)
                self._push(command)
        else: # Now we have to add all converted records to the existing tag
            # The easiest way to do this is to remove all records and add the converted records again
            for record in self.inner.tags[oldTag]:
                newRecord = record.copy()
                newRecord.tag = newTag
                newRecord.value = oldTag.type.convertValue(newTag.type,record.value)
                self.addRecord(newRecord)
            # Finally remove the old tag
            self.removeTag(oldTag)

        self._endMacro()
            
        return True

    def getTagsOfElement(self,element):
        """Return the tags of the given element as stored in the records."""
        result = tags.Storage()
        for tag,records in self.inner.tags.items():
            for record in records:
                if element in record.elementsWithValue:
                    result.add(tag,record.value)
        return result
                    
    def getChanges(self):
        """Return the changes between the tags as stored in the records and the tags in database/filesystem
        or in the editor. This method may only be used if saveDirectly is False."""
        if self.saveDirectly:
            raise RuntimeError("You must not call save in a TagEditorModel that saves directly.")
            
        return {element.id: (element.originalTags,self.getTagsOfElement(element))
                for element in self.inner.elements}
        
    def _checkCommonAndMove(self,record,undoable):
            # Maybe we have to move the record as the common records are sorted to the top
            pos = self.inner.tags[record.tag].index(record)
            border = self._commonCount(record.tag)
            if (record.isCommon() and pos < border) or (not record.isCommon() and pos >= border):
                return # nothing to do
            newPos = border - 1 if record.isCommon() else border
            if not undoable:
                self.inner.moveRecord(record.tag,pos,newPos)
            else:
                command = UndoCommand(self,self.inner.moveRecord,pos,newPos)
                self._push(command)
                
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
            
    def _handleDispatcher(self,event):
        """React to change events. We have to
        
            - delete elements on ElementsDeletedEvents,
            - change all affected records on TagTypeChangedEvent. Furthermore the tag is used as a key in
              self.inner.tags and must be updated here, too.
            - React to events that change tags.
             
        \ """
        if isinstance(event,modify.events.ElementsDeletedEvent):
            affectedElements = [el for el in self.inner.elements if el.id in event.ids()]
            if len(affectedElements) > 0:
                # All records store a reference to this list, so this will update them, too.
                self.inner.elements = [el for el in self.inner.elements if el not in affectedElements]
                if len(self.inner.elements) == 0:
                    self.createRecords()
                    return
                for tag in list(self.inner.tags.keys()): # dict may change
                    for record in self.inner.tags[tag][:]: # list may change
                        remaining = [element for element in record.elementsWithValue
                                        if element not in affectedElements]
                        if len(remaining) == 0:
                            self.inner.removeRecord(record)
                        elif len(remaining) < len(record.elementsWithFlag):
                            self.inner.changeRecord(record.tag,record,
                                            Record(record.tag,record.value,self.inner.elements,remaining))
                    if len(self.inner.tags) == 0:
                        self.inner.removeTag(tag)
            return
        
        elif isinstance(event,modify.events.ElementChangeEvent):
            if event.level != self.level:
                return
            affected = [el for el in self.inner.elements if el.id in event.ids()]
            if isinstance(event,modify.events.SingleTagChangeEvent):
                if isinstance(event,modify.events.TagValueAddedEvent):
                    self._addElementsWithValue(event.tag,event.value,affected)
                elif isinstance(event,modify.events.TagValueRemovedEvent):
                    self._removeElementsWithValue(event.tag,event.value,affected)
                elif isinstance(event,modify.events.TagValueChangedEvent):
                    self._removeElementsWithValue(event.tag,event.oldValue,affected)
                    self._addElementsWithValue(event.tag,event.newValue,affected)
                # Finally update the title attribute
                if event.tag == tags.TITLE and len(affected) > 0:
                    for element in affected:
                        elementTags = self.getTagsOfElement(element)
                        if tags.TITLE in elementTags:
                            element.title = element.getTitle(titles=elementTags[tags.TITLE])
                        else: element.title = element.getTitle() # Will produce something like 'No title'
                    self.titlesChanged.emit(affected)
                    
            elif event.tagsChanged:          
                # General ElementChangeEvent
                if not any(element.id in event.ids() for element in self.inner.elements):
                    return
                # Contrary to the detailed event handling above, we do a very simple thing here: We store the
                # tags in the elements and load them anew using createRecords.
                for element in self.inner.elements:
                    if element.id in event.ids():
                        # No need to copy because the tags will be deleted in createRecords in a moment.
                        element.tags = event.getTags(element.id)
                    else: element.tags = self.getTagsOfElement(element)
                self.createRecords() # This will directly remove the tags-attributes again
        
        # else: It is not necessary to process TagTypeChangedEvents because the tag's single instance is
        # updated automatically and the GUI reacts to the signal itself.
        
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
        splittedValues = record.value.split(separator)
        if len(splittedValues) == 0:
            return True # Nothing to split...thus the split was successful :-)
        if not all(record.tag.isValid(value) for value in splittedValues):
            return False
            
        # Now here starts the split
        pos = self.inner.tags[record.tag].index(record)
        self._beginMacro(self.tr("Split"))
        # First remove the old value
        command = UndoCommand(self,self.inner.removeRecord,record)
        self._push(command)
        # Now create new records and insert them at pos
        for value in splittedValues:
            newRecord = record.copy()
            newRecord.value = value
            # This is false if the record was added to an already existing one
            if self._insertRecord(pos,newRecord):
                pos = pos + 1
        self._endMacro()
        return True

    def splitMany(self,records,separator):
        """Split each of the given records using *separator*. Return true if all splits were successful."""
        self._beginMacro(self.tr("Split many"))
        result = any(self.split(record,separator) for record in records)
        self._endMacro()
        return result

    def editMany(self,records,newValues):
        """Given a list of records and an equally long list of values change the value of the i-th record to
        the i-th value."""
        self._beginMacro(self.tr("Edit many"))
        for record, value in zip(records,newValues):
            newRecord = record.copy()
            newRecord.value = value
            command = UndoCommand(self,self.inner.changeRecord,record.tag,record,newRecord)
            self._push(command)
        self._endMacro()

    def extendRecords(self,records):
        """Make the given records common, i.e. set ''record.elementsWithValue'' to all elements."""
        self._beginMacro(self.tr("Extend records"))
        commonChangedTags = set() # Set of tags where the number of common records changed
        for record in records:
            if record.isCommon():
                continue
            else: commonChangedTags.add(record.tag)
            
            # Maybe we have to change the record's position, since it is common afterwards
            pos = self.inner.tags[record.tag].index(record)
            newPos = self._commonCount(record.tag)
            
            newRecord = record.copy()
            newRecord.elementsWithValue = self.inner.elements[:] # copy the list!
            command = UndoCommand(self,self.inner.changeRecord,record.tag,record,newRecord)
            self._push(command)
            
            if pos != newPos:
                command = UndoCommand(self,self.inner.moveRecord,record.tag,pos,newPos)
                self._push(command)
        self._endMacro()
        
        for tag in commonChangedTags:
            self.commonChanged.emit(tag)

    def _commonCount(self,tag):
        """Return the number of records of the given tag that are common (i.e. all elements have the
        record's value)."""
        return sum(record.isCommon() for record in self.inner.tags[tag])
