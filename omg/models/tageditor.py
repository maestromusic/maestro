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

from .. import application, constants, utils
from ..core import levels, tags

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
        - elementsWithValue: a sublist of elements that have a tag of this value
    
    This data model resembles much more the graphical structure of the tageditor. A Record is considered
    immutable by the Undo-/Redo-system.
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
    
    def merge(self,other):
        """Return a copy of this record which contains the union of the elementsWithValue of this record and
        the record *other*."""
        elements = list(self.elementsWithValue)
        elements.extend(el for el in other.elementsWithValue if el not in elements)
        return Record(self.tag,self.value,self.allElements,elements)
    
    def __str__(self):
        if self.isCommon():
            return str(self.value)
        elif len(self.elementsWithValue) == 1:
            return translate("TagEditor","{} in {}").format(self.value,self.elementsWithValue[0])
        elif len(self.getExceptions()) == 1:
            return translate("TagEditor","{} except in {}").format(self.value,self.getExceptions()[0])
        else: return translate("TagEditor","{} in {} pieces").format(self.value,len(self.elementsWithValue))

    
class RecordModel(QtCore.QObject):
    """A RecordModel is basically the data-structure used by the tageditor. It stores an OrderedDict mapping
    tags to lists of records (similar to the tageditor's GUI). It provides a set of basic commands to change
    the data and will emit signals when doing so. The lists of Records can be accessed via item access:
    
        recordModel[tags.get('artist')]
        
    Intentionally the commands of RecordModel are very basic, so that each command can be undone easily.
    In contrast to the TagEditorModel the RecordModel does not do any Undo/Redo-stuff. Instead,
    TagEditorModel splits its complicated actions into several calls of the methods of RecordModel which are
    assembled into an TagEditorUndoCommand.
    
    Another advantage of having only basic commands is that the GUI has only to react to basic signals.
    
    An effect of this design is that RecordModel may have states that would be inconsistent for
    TagEditorModel (e.g. a tag with empty record list, or records with tag A in ''self._records[tag B]'').
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
        """Return the list of tags contained in this model. Basically an alias for keys but this method
        really returns a list and not a key-view. Additionally its name is more descriptive."""
        return list(self._records.keys())
        
    def setRecords(self,records):
        """Set the records of this RecordModel."""
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
      
        
class TagFlagEditorUndoCommand(QtGui.QUndoCommand):
    """Abstract super class of the UndoCommands used by FlagEditorModel and TagEditorModel. The following
    discussion uses tags, but the same procedure is used for flags.
     
    Changes in the tageditor have to be stored at two places: In the level (which may include changing
    database and filesystem) and in the RecordModel used by the TagEditorModel. The latter can in principle
    be done by simply reacting to the ElementChangedEvent triggered by the former. But this can lead to
    unexpected results like records jumping around because the order has changed.
    
    Therefore the tageditor uses a more complicated Undo-/Redo-system using its own kind of UndoCommands --
    the TagEditorUndoCommand. Such a command will change the level and additionally change the records by
    himself (keeping records at the correct position).
    
    A TagEditorUndoCommand stores a list of methods of the RecordModel and associated argument lists for redo.
    It will automatically compute the appropriate methods and arguments for the undo as well as a list of
    changed ids for the event.
    On redo/undo the following steps happen:
    
        - the methods are invoked with their arguments
        - the level is changed according to the list of methods and arguments.
        - then a single event for all changes done by the methods is emitted. This event contains the list
          of methods and arguments.

    To compose a TagEditorUndoCommand, use addMethod (one or more times) and finally push it on the stack.
    
    Two problems remain:
        
        - Which methods should be added to a command often depends on the effects of methods previously added.
          Thus when adding a method to the command it must be executed directly. At the first redo we have to
          take care that the methods are not executed a second time (this is done by self._firstRedo).
        - A TagEditorUndoCommand must not change records by himslef after records have been changed by an
          external source (e.g. the tageditor's set of elements has changed or it reacted to an
          ElementChangeEvent by another source). The records that should be changed by the
          TagEditorUndoCommand may simply not exist anymore. To solve this problem the TagEditor will store
          an integer _statusNumber that is increased every time such a change happens. A TagEditorUndoCommand
          will store the number when it is created and only change records by himself if the numbers match.
          
    """
    def __init__(self,model,text):
        super().__init__(text)
        self._firstRedo = True
        self.model = model
        self._statusNumber = self.model._statusNumber
        self.redoMethods = []
        self.undoMethods = []
        self.ids = []

    def addMethod(self,method,*params):
        """Add a method of the RecordModel to this command. On redo change the level according to the methods
        and arguments added to this command. When the tageditor reacts to the ChangeEvent generated by the
        redo, execute the methods with the corresponding arguments to update the records.
        """ 
        self.redoMethods.append((method,params))
        self.undoMethods.append(self._computeUndoMethod(method,params))
        method(*params)

    def _computeUndoMethod(self,method,*params):
        """Compute the method and arguments that will undo the change made by *method* invoked with *params*
        and return them as a tuple.
        
        Furthermore update the list of ids stored in this command to include those elements that will be
        changed by *method*.
        """
        raise NotImplementedError()

    def redo(self):
        if len(self.redoMethods):
            for method,params in self.redoMethods:
                if not self._firstRedo and self._statusNumber == self.model._statusNumber:
                    method(*params)
                self.modifyLevel(method,params)
            event = levels.ElementChangedEvent(dataIds=self.ids) #TagFlagEditorChangedEvent(self,self.redoMethods)
            self.model.level.changed.emit(event)
        self._firstRedo = False

    def undo(self):
        if len(self.undoMethods):
            for method,params in reversed(self.undoMethods):
                if self._statusNumber == self.model._statusNumber:
                    method(*params)
                self.modifyLevel(method,params)
            event = levels.ElementChangedEvent(dataIds=self.ids) #TagFlagEditorChangedEvent(self,self.undoMethods)
            self.model.level.changed.emit(event)

    def modifyLevel(self,method,params):
        """Modify the level according to *method* and *params*: The change to the level must be the same
        that is done to the records when *method* is invoked with *params*."""
        raise NotImplementedError()
        
        
class TagEditorUndoCommand(TagFlagEditorUndoCommand):
    """UndoCommands used by the RagEditor. See TagFlagEditorUndoCommand."""
    def _computeUndoMethod(self,method,params):
        recordModel = self.model.records
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
        return undoMethod,undoParams

    def _updateIds(self,record):
        """Add the ids of all elements of *record* to the ids of this command. Use this in _computeUndoMethod
        to update the list of changed ids."""
        self.ids.extend(element.id for element in record.elementsWithValue if element.id not in self.ids)
        
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
                        
                        
class TagEditorModel(QtCore.QObject):
    """A model built for the Record-based GUI of the tageditor. It stores
    
        - a list of elements that are currently edited.
        - a RecordModel storing the records built from the tags of these elements
        
    Due to this different data structure, TagEditorModel cannot simply redo/undo actions appropriately by
    reacting to general ElementChangedEvents. Therefore it uses a somewhat complicated system:
    
    When a record-changing method is called, an TagEditorUndoCommand is created and pushed onto the stack.
    Then a series of methods of the RecordModel is added to the command and directly executed, changing the
    records as well as the underlying level (but without emitting an event). When the command is finished, a
    single ElementChangedEvent is emitted.
    
    When a record-changing method is called, an TagEditorUndoCommand is created. Then a series of methods of
    the RecordModel is added to the command and directly executed, changing the records but not yet the level.
    It is important to change the record directly because the next method added to the command might depend
    on the effect of the previous one. When the command is finally composed, it is pushed onto the stack and
    the level is changed according to the stored methods. A single ElementChangedEvent is emitted.
    
    On later redos all methods of the command are executed changing records and level and an event is emitted.
    On undos an appropriate list of undo methods computed by the command is executed and an event is emitted.
    In both cases the command only changes the RecordModel if its status is still the same, i.e. the list of
    records has not been changed by an external source (e.g. by selecting different elements).
    
    Nethertheless a TagEditorModel must react to ChangeEvents sent from the level because tags may have
    changed by an external source or by an TagEditorUndoCommand that is too old to change records directly
    (see the discussion of _statusNumber in the docstring of TagFlagEditorUndoCommand).
    
    Model parameters are:
    
        - level: the level that contains the elements
        - elements: a list of elements whose flags will be displayed and edited by this model.
        - stack: An undo stack or None, in which case the global stack will be used (only use your own stacks
          in modal dialogs)
    """
    resetted = QtCore.pyqtSignal()
    
    def __init__(self,level=None,elements=None,stack=None):
        QtCore.QObject.__init__(self)
            
        self._statusNumber = 0
        
        self.records = RecordModel()
        self.tagInserted = self.records.tagInserted
        self.tagRemoved = self.records.tagRemoved
        self.tagChanged = self.records.tagChanged
        self.recordInserted = self.records.recordInserted
        self.recordRemoved = self.records.recordRemoved
        self.recordChanged = self.records.recordChanged
        self.recordMoved = self.records.recordMoved
        self.commonChanged = self.records.commonChanged
        
        self.level = None # will be set in self.setElements
        if elements is None:
            elements = []
        self.setElements(level,elements)
        
        if stack is None:
            self.stack = application.stack
        else: self.stack = stack

    def getTags(self):
        """Return the list of tags that are present in any of the elements currently edited."""
        return list(self.records.keys())

    def getRecords(self,tag):
        """Return the list of records with the given tag."""
        return self.records[tag]

    def getElements(self):
        """Return a list of all elements currently being edited in the tageditor."""
        return self.elements
    
    def setElements(self,level,elements):
        """Set the list of elements currently edited and reset the tageditor."""
        self._statusNumber += 1
        if self.level != level:
            if self.level is not None:
                self.level.changed.connect(self._handleLevelChanged)
            if level is not None:
                level.changed.connect(self._handleLevelChanged)
        self.level = level
        self.elements = elements
        records = self._createRecords()
        self.records.setRecords(records.values())
        self.resetted.emit()

    def _createRecords(self):
        """Create records for self.elments. Return them as dict mapping (tag,value)-tuples to records."""
        records = {}
        for element in self.elements:
            for tag in element.tags:
                for value in element.tags[tag]:
                    if (tag,value) in records:
                        records[(tag,value)].elementsWithValue.append(element)
                    else: records[(tag,value)] = Record(tag,value,self.elements,[element])
        return records

    def getTagsOfElement(self,element):
        """Return the tags of the given element as stored in the records."""
        result = tags.Storage()
        for tag,records in self.records.items():
            for record in records:
                if element in record.elementsWithValue:
                    result.add(tag,record.value)
        return result

    def addRecord(self,record):
        """Add a record to the model. If there is already a record with same tag and value the elements
        with that value will be merged from both records."""
        command = TagEditorUndoCommand(self,self.tr("Add record"))
        result = self._insertRecord(command,None,record)
        self.stack.push(command)

    def _insertRecord(self,command,pos,record):
        """Insert a record at the position *pos*. This is a helper function used by e.g. addRecord. It does
        not start a new command and should therefore not be used from outside this class."""
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
            command.addMethod(self.records.insertRecord,pos,record)
        else:
            # Now things get complicated: Add the record's elements to those of (a copy of)
            # the existing record.
            copy = existingRecord.merge(record)
            if copy.elementsWithValue != existingRecord.elementsWithValue:
                command.addMethod(self.records.changeRecord,record.tag,existingRecord,copy)
                # If this makes the record common, move it to the right place
                if existingRecord.isCommon() != copy.isCommon():
                    self._checkCommonAndMove(command,copy)
            
    def removeRecord(self,record):
        """Remove a record from the model."""
        self.removeRecords([record])
        
    def removeRecords(self,records):
        """Remove several records from the model."""
        if len(records) > 0:
            command = TagEditorUndoCommand(self,self.tr("Remove record(s)",'',len(records)))
            for record in records:
                self._removeRecord(command,record)
            self.stack.push(command)

    def _removeRecord(self,command,record):
        """Add methods to the given UndoCommand that will remove *record*."""
        command.addMethod(self.records.removeRecord,record)
        if len(self.records[record.tag]) == 0:
            command.addMethod(self.records.removeTag,record.tag)
            
    def changeRecord(self,oldRecord,newRecord):
        """Change the record *oldRecord* into *newRecord*. This method will handle all complicated stuff that
        can happen (e.g. when oldRecord.tag != newRecord.tag or when a record with the same tag and value as
        *newReword* does already exist).
        """
        command = TagEditorUndoCommand(self,self.tr("Change record"))

        # If the tag has changed or the new value does already exist, we simply remove the old and add the
        # new record. Otherwise we really change the record so that its position stays the same because this
        # is what the user expects.
        existingRecord = self.records.get(newRecord.tag,newRecord.value)
        if oldRecord.tag != newRecord.tag or (existingRecord is not None and existingRecord is not oldRecord):
            # This is a complicated change and the record has no chance to stay in the same position.
            # Thus we simply remove the old and add the new
            self._removeRecord(command,oldRecord)
            self._insertRecord(command,None,newRecord)
        else: 
            # Simple: Tag is unchanged and either there is no record with newRecord.value or the value
            # remains unchangend (thus only elementsWithValue changed)
            command.addMethod(self.records.changeRecord,oldRecord.tag,oldRecord,newRecord)
            self._checkCommonAndMove(command,newRecord)
        self.stack.push(command)

    def removeTag(self,tag):
        """Remove all records with tag *tag*."""
        command = TagEditorUndoCommand(self,self.tr("Remove tag"))
        # First remove all records
        while len(self.records[tag]) > 0:
            command.addMethod(self.records.removeRecord,self.records[tag][0])
        # Remove the empty tag
        command.addMethod(self.records.removeTag,record.tag)
        self.stack.push(command)

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

        self.stack.push(command)
        return True
        
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
        result = any(self._split(command,record,separator) for record in records)
        self.stack.push(command)
        return result
    
    def _split(self,command,record,separator):
        """Helper function for split and splitMany: Add methods to *command* that will split *record* at the
        given separator."""
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
        """Given a list of records and an equally long lists of values, change the value of the i-th record
        to the i-th value."""
        command = TagEditorUndoCommand(self,self.tr("Edit many"))
        for record, value in zip(records,newValues):
            newRecord = record.copy()
            newRecord.value = value
            command.addMethod(self.records.changeRecord,record.tag,record,newRecord)
        self.stack.push(command)

    def extendRecords(self,records):
        """Make the given records common, i.e. set 'record.elementsWithValue' to all elements."""
        command = TagEditorUndoCommand(self,self.tr("Extend records"))

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
                command.addMethod(self.records.moveRecord,record.tag,pos,newPos)
        self.stack.push(command)

    def _checkCommonAndMove(self,command,record):
        """Check whether *record* is at a valid position (uncommon records come after common ones) and if
        not, move it to a valid position. If *command* is not None, add a method to it that will do the move.
        """
        pos = self.records[record.tag].index(record)
        border = self._commonCount(record.tag)
        if (record.isCommon() and pos < border) or (not record.isCommon() and pos >= border):
            return # nothing to do
        newPos = border - 1 if record.isCommon() else border
        if command is None:
            self.records.moveRecord(record.tag,pos,newPos)
        else: command.addMethod(self.records.moveRecord,record.tag,pos,newPos)
        
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
        
    def _commonCount(self,tag):
        """Return the number of records of the given tag that are common (i.e. all elements have the
        record's value)."""
        return sum(record.isCommon() for record in self.records[tag])

    def _handleLevelChanged(self,event):
        """React to change events fo the underlying level."""
        currentIds = [el.id for el in self.elements]
        if all(id not in currentIds for id in event.dataIds):
            return # not our problem

        changed = False
        actualRecords = self._createRecords()
        
        for tag in self.records.tags():
            for myRecord in list(self.records[tag]):
                if (tag,myRecord.value) not in actualRecords:
                    self.records.removeRecord(myRecord)
                    if len(self.records[myRecord.tag]) == 0:
                        self.records.removeTag(myRecord.tag)
                    changed = True
                else:
                    actualRecord = actualRecords[(tag,myRecord.value)]
                    if actualRecord.elementsWithValue != myRecord.elementsWithValue:
                        self.records.changeRecord(myRecord.tag,myRecord,actualRecord)
                        changed = True
                    del actualRecords[(tag,myRecord.value)]
        
        # Finally add all records that remained
        for actualRecord in actualRecords.values():
            if actualRecord.tag not in self.records.tags():
                self.records.insertTag(len(self.records.tags()),actualRecord.tag)
            self.records.insertRecord(len(self.records[actualRecord.tag]),actualRecord)
            changed = True
        
        if changed:
            # After a single change to the records that is not stored in TagEditorUndoCommands, we must not
            # allow existing TagEditorUndoCommands to change the records directly.
            self._statusNumber += 1
