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

import collections, itertools

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
        - allElements: a tuple of all elements that are currently edited by the tageditor.
        - elementsWithValue: a tuple of elements that have a tag of this value. 
                             Must be a subset of allElements.
    
    This data model resembles much more the graphical structure of the tageditor. A Record is considered
    immutable by the Undo-/Redo-system.
    """
    def __init__(self,tag,value,allElements,elementsWithValue):
        self.tag = tag
        self.value = value
        self.allElements = allElements
        assert isinstance(elementsWithValue,tuple)
        self.elementsWithValue = elementsWithValue
    
    def copy(self):
        """Return a copy of this record."""
        return Record(self.tag,self.value,self.allElements,self.elementsWithValue)
        
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
    
    def __repr__(self):
        if self.isCommon():
            return str(self.value)
        elif len(self.elementsWithValue) == 1:
            return translate("TagEditor","{} in {}").format(self.value,self.elementsWithValue[0])
        elif len(self.getExceptions()) == 1:
            return translate("TagEditor","{} except in {}").format(self.value,self.getExceptions()[0])
        else: return translate("TagEditor","{} in {} pieces").format(self.value,len(self.elementsWithValue))
    
    @staticmethod
    def merge(first,second):
        """Merge two records: The result will contain tag and value of *first* and the union of the
        elementsWithValue-lists of both records. If the elements of *second* form a subset of those of
        *first*, this method will simply return *first*."""
        newElements = [el for el in second.elementsWithValue if not el in first.elementsWithValue]
        if len(newElements) > 0:
            elementsWithValue = tuple(itertools.chain(first.elementsWithValue,newElements))
            return Record(first.tag,first.value,first.allElements,elementsWithValue)
        else:
            return first
        
    def __eq__(self, other):
        return self.tag == other.tag and self.value == other.value and \
            self.elementsWithValue == other.elementsWithValue
    
    def __ne__(self, other):
        return self.tag != other.tag or self.value != other.value or \
            self.elementsWithValue != other.elementsWithValue
    
    
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

    def __getitem__(self,key):
        return self._records[key]

    def __setitem__(self,key,value):
        self._records[key] = value

    def __delitem__(self,key):
        del self._records[key]

    def keys(self):
        # Note that we use utils.OrderedDict and therefore keys will return a list and no view
        return self._records.keys()
    
    # Simply a more descriptive name
    tags = keys

    def values(self):
        return self._records.values()

    def items(self):
        return self._records.items()
        
    def setRecords(self,records):
        """Set the records of this RecordModel."""
        self._records = records
        
    def copy(self,tag=None):
        """Return a copy of this model. If *tag* is given, only the records of this tag are copied."""
        copy = RecordModel()
        copy._records = utils.OrderedDict()
        if tag is None:
            for tag,records in self._records.items():
                copy._records[tag] = list(records) # the actual records are immutable and need not be copied
        else: copy._records[tag] = list(self._records[tag])
        return copy

    def insertRecord(self,pos,record):
        """Insert *record* at position *pos* into the list of records with tag record.tag. This list must
        exist before you call this method, so you may need to call insertTag first. *pos* may also be -1."""
        assert record.tag in self._records
        if pos == -1:
            pos = len(self._records[record.tag])
        self._records[record.tag].insert(pos,record)
        self.recordInserted.emit(pos,record)

    def removeRecord(self,record):
        """Remove a record from the model."""
        pos = self._records[record.tag].index(record)
        del self._records[record.tag][pos]
        self.recordRemoved.emit(record)
    
    def changeRecord(self,tag,oldRecord,newRecord):
        """Replace the record *oldRecord* by *newRecord*. The replacement will take place in the list of
        records with tag *tag*, regardless of the tags stored in the records (those tags may differ)."""
        pos = self._records[tag].index(oldRecord)
        self._records[tag][pos] = newRecord
        self.recordChanged.emit(tag,oldRecord,newRecord)
        
    def insertTag(self,pos,tag):
        """Insert the given tag at position *pos* into the OrderedDict. The list of records will be empty.
        *pos* may also be -1."""
        if pos == -1:
            pos = len(self._records)
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
        assert oldTag in self._records and newTag not in self._records
        self._records.changeKey(oldTag,newTag)
        self.tagChanged.emit(oldTag,newTag)
    
   
class TagEditorUndoCommand:
    """Special UndoCommand for the TagEditor. It is used together in a macro with a normal undocommand
    created by Level.changeTags to update the internal structure of the tageditor accordingly. When the
    macro is finished and an LevelChangedEvent is emitted, the tageditor will detect that it is already
    up-to-date and do nothing. Without TagEditorUndoCommand it would have to compute the appropriate change
    of its internal structure from the changed ids. This is difficult and in some cases even impossible. 
    
    Arguments are
        
        - the model in which the change is done,
        - a method from ['insertRecord','removeRecord','changeRecord','insertTag','removeTag','changeTag'],
        - a dict with key-word arguments to that method.
    """
    def __init__(self, model, method, args):
        self.model = model
        self.method = method
        self.args = args
        self.undoMethod, self.undoArgs = self._computeUndoMethod(method,args)
        self.text = '' # no text necessary as these are always used in macros
        
    def redo(self):
        getattr(self.model.records, self.method)(**self.args)
        
    def undo(self):
        getattr(self.model.records, self.undoMethod)(**self.undoArgs)
    
    def _computeUndoMethod(self,method,args):
        """Given a method and a dict of arguments, return the appropriate method and arguments to the first
        method."""
        recordModel = self.model.records
        if method == 'insertRecord':
            undoMethod = 'removeRecord'
            undoArgs = {'record': args['record']}
        elif method == 'removeRecord':
            record = args['record']
            undoMethod = 'insertRecord'
            undoArgs = {'pos': recordModel[record.tag].index(record), 'record': record}
        elif method == 'changeRecord':
            undoMethod = 'changeRecord'
            undoArgs = {'tag': args['tag'], 'oldRecord': args['newRecord'], 'newRecord': args['oldRecord']}
        elif method == 'insertTag':
            undoMethod = 'removeTag'
            undoArgs = {'tag': args['tag']}
        elif method == 'removeTag':
            tag = args['tag']
            undoMethod = 'insertTag'
            undoArgs = {'pos': recordModel.tags().index(tag), 'tag': tag}
        elif method == 'changeTag':
            undoMethod = 'changeTag'
            undoArgs = {'oldTag': args['newTag'], 'newTag': args['oldTag']}
        return undoMethod,undoArgs
    
    
class TagEditorModel(QtCore.QObject):
    """A model built for the Record-based GUI of the tageditor. It stores
    
        - a list of elements that are currently edited.
        - a RecordModel storing the records built from the tags of these elements
    
    The fundamental problem with the TagEditorModel is that it contains data that is not stored in the level:
    the order of the records in each tag and the order of tags. This order is important for a convenient
    GUI (otherwise new or changed records would always be appended at the end, records might jump around...).
    
    Due to this different data structure, TagEditorModel uses TagEditorUndoCommands to change its internal
    structure together with the tags of elements.
    
    Change by the user in GUI -> method of TagEditorModel (e.g. addRecord) -> in one macro Level.changeTags
    is called and a TagEditorUndoCommand is created -> at the end of the macro a LevelChangedEvent is
    emitted -> The TagEditorModel receives the event and does nothing, because its structure has already
    been updated.
    
    Of course the tageditor has to react to change events from other sources.
    
    This procedure has one caveat: Whenever the set of elements in the tageditor changes or the tageditor
    reacts to a change event that did not originate in the tageditor, the records of the tageditor change
    without an UndoCommand. Thus all TagEditorUndoCommands on the stack could fail now. Therefore all these
    commands are added via a substack and removed when the records of the tageditor changes outside of
    undo/redo.
    
    Model parameters are:
    
        - level: the level that contains the elements
        - elements: a list of elements whose flags will be displayed and edited by this model.
        - stack: An undo stack or None, in which case the global stack will be used (only use your own stacks
          in modal dialogs)
    """
    resetted = QtCore.pyqtSignal()
    
    def __init__(self, level=None, elements=None, stack=None):
        QtCore.QObject.__init__(self)
        
        self.records = RecordModel()
        self.tagInserted = self.records.tagInserted
        self.tagRemoved = self.records.tagRemoved
        self.tagChanged = self.records.tagChanged
        self.recordInserted = self.records.recordInserted
        self.recordRemoved = self.records.recordRemoved
        self.recordChanged = self.records.recordChanged
        
        if stack is None:
            self.stack = application.stack
        else: self.stack = stack
        self.substack = self.stack.createSubstack()
        
        self.level = None # will be set in self.setElements
        if elements is None:
            elements = []
        self.setElements(level,elements)

    def getTags(self):
        """Return the list of tags that are present in any of the elements currently edited."""
        return list(self.records.keys())

    def getRecords(self, tag):
        """Return the list of records with the given tag."""
        return self.records[tag]

    def getElements(self):
        """Return a list of all elements currently being edited in the tageditor."""
        return self.elements
    
    def setElements(self, level, elements):
        """Set the list of elements currently edited and reset the tageditor."""
        self.substack.reset()
        if self.level != level:
            if self.level is not None:
                self.level.disconnect(self._handleLevelChanged)
            if level is not None:
                level.connect(self._handleLevelChanged)
        self.level = level
        self.elements = tuple(elements)
        self.records.setRecords(self._createRecords())
        self.resetted.emit()

    def _createRecords(self):
        """Create records for self.elments. Return them as an ordered dict mapping tag-instances to
        list of records."""
        # While building the elementLists we use an ordered dict (value->record) for each tag to make lookups
        # faster while keeping the order in which the values are found.
        elementLists = {}
        for element in self.elements:
            for tag in element.tags:
                if tag not in elementLists:
                    elementLists[tag] = collections.OrderedDict()
                for value in element.tags[tag]:
                    if value not in elementLists[tag]:
                        elementLists[tag][value] = [element]
                    else: elementLists[tag][value].append(element)
        
        # The final result should of course be a dict (tag->list of records). The dict should first
        # contain all internal tags, then the rest.
        result = utils.OrderedDict()
        for tag in itertools.chain(tags.tagList,elementLists.keys()):
            if tag in result or tag not in elementLists:
                continue # due to the chain some tags may appear twice
            result[tag] = []
            for value, elementsWithValue in elementLists[tag].items():
                if len(elementsWithValue) == len(self.elements):
                    elementsWithValue = self.elements # save memory
                else: elementsWithValue = tuple(elementsWithValue)
                result[tag].append(Record(tag,value,self.elements,elementsWithValue))
        return result

    def _command(self, method, **args):
        """Helper function: Change tags in the level and push a TagEditorUndoCommand to change the internal
        structure accordingly. *method* is the name of a method of RecordModel and *args* are the keyword
        arguments for that method. The appropriate undo-method and arguments are computed automatically.
        """
        if method == 'insertRecord':
            record = args['record']
            diff = tags.TagDifference(additions=[(record.tag,record.value)])
            self.level.changeTags({element: diff for element in record.elementsWithValue})
        elif method == 'removeRecord':
            record = args['record']
            diff = tags.TagDifference(removals=[(record.tag,record.value)])
            self.level.changeTags({element: diff for element in record.elementsWithValue})
        elif method == 'changeRecord':
            oldRecord = args['oldRecord']
            newRecord = args['newRecord']
            
            oldElements = set(oldRecord.elementsWithValue)
            newElements = set(newRecord.elementsWithValue)
            removeList = list(oldElements - newElements)
            addList = list(newElements - oldElements)
            if len(removeList):
                diff = tags.TagDifference(removals=[(oldRecord.tag,oldRecord.value)])
                self.level.changeTags({element: diff for element in removeList})
            if len(addList):
                diff = tags.TagDifference(additions=[(newRecord.tag,newRecord.value)])
                self.level.changeTags({element: diff for element in addList})
                
            if oldRecord.tag != newRecord.tag or oldRecord.value != newRecord.value:
                changeList = list(newElements.intersection(oldElements))
                if len(changeList):
                    if oldRecord.tag != newRecord.tag:
                        diff = tags.TagDifference(additions=[(newRecord.tag,newRecord.value)],
                                                  removals=[(oldRecord.tag,oldRecord.value)])
                    else:
                        diff = tags.TagDifference(replacements=[(oldRecord.tag,oldRecord.value,
                                                                 newRecord.value)])
                    self.level.changeTags({element: diff for element in changeList})

        self.substack.push(TagEditorUndoCommand(self, method, args))
        
    def addRecord(self, record):
        """Add a record to the model. If there is already a record with same tag and value the elements
        with that value will be merged from both records."""
        self.stack.beginMacro(self.tr("Add record"))
        self._insertRecord(-1,record)
        self.stack.endMacro()

    def _insertRecord(self, pos, record):
        """Helper function for inserting: Push commands to the stack that will insert *record* at *pos*
        into the list of records of tag record.tag. *pos* may be -1.
        Take care that the tag is created if it does not exist and that the record is merged with an existing
        one with the same tag and value.
        """
        if record.tag not in self.records.tags():
            self._command('insertTag', pos=-1, tag=record.tag)
        # First check whether there exists already a record with the same value
        if record.tag in self.records.tags():
            for existingRecord in self.records[record.tag]:
                if existingRecord.value == record.value:
                    newRecord = Record.merge(existingRecord,record)
                    self._command('changeRecord', tag=existingRecord.tag,
                                  oldRecord=existingRecord, newRecord=newRecord)
                    return
        self._command('insertRecord', pos=pos, record=record)
            
    def removeRecord(self, record):
        """Remove a record from the model."""
        self.stack.beginMacro(self.tr("Remove record"))
        self._removeRecord(record)
        self.stack.endMacro()
        
    def removeRecords(self, records):
        """Remove several records from the model."""
        if len(records) > 0:
            self.stack.beginMacro(self.tr("Remove %n record(s)",'',len(records)))
            for record in records:
                self._removeRecord(record)
            self.stack.endMacro()

    def _removeRecord(self, record):
        """Helper method for removing: Push commands to the stack that will remove *record* and its tag
        if it is empty."""
        removeTag = len(self.records[record.tag]) == 1
        self._command('removeRecord', record=record)
        if removeTag: 
            self._command('removeTag', tag=record.tag)
            
    def changeRecord(self, oldRecord, newRecord):
        """Change the record *oldRecord* into *newRecord*. This method will handle all complicated stuff that
        can happen (e.g. when oldRecord.tag != newRecord.tag or when a record with the same tag and value as
        *newReword* does already exist).
        """
        self.stack.beginMacro(self.tr("Change record"))

        if oldRecord.tag != newRecord.tag:
            self._removeRecord(oldRecord)
            self._insertRecord(-1, newRecord)
        else:
            self._changeRecord(oldRecord, newRecord)
        self.stack.endMacro()
        
    def _changeRecord(self, oldRecord, newRecord):
        """Helper function for changing: Push commands to the stack that will change *oldRecord* into
        *newRecord*. Both records must have the same value. Handle the case that there exists already a
        record whose value equals newRecord.value.
        """
        assert oldRecord.tag == newRecord.tag
        for existingRecord in self.records[oldRecord.tag]:
            if existingRecord.value == newRecord.value:
                break
        else: existingRecord = None
        if existingRecord is not None and existingRecord is not oldRecord:
            self._command('removeRecord', record=oldRecord)
            self._insertRecord(-1, newRecord)
        else: 
            # either no record with the new value exists or only the elementsWithValue changed
            self._command('changeRecord', tag=oldRecord.tag, oldRecord=oldRecord, newRecord=newRecord)

    def removeTag(self,tag):
        """Remove all records with tag *tag*."""
        self.stack.beginMacro(self.tr("Remove tag"))
        # First remove all records
        for record in self.records[tag]:
            # Note that this does not really change the list
            # until the macro is finished and the event is processed 
            self._command('removeRecord', record=record)
        # Remove the empty tag
        self._command('removeTag', tag=tag)
        self.stack.endMacro()

    def changeTag(self, oldTag, newTag):
        """Change tag *oldTag* into *newTag*. This will convert the values and tags of the affected records
        and handle special cases (e.g. when one of the values is already present in *newTag*).
        If the conversion of any of the values fails, this method will do nothing and return False. After a
        successful change it will return true.
        """
        # First check whether the existing values in oldTag are convertible to newTag
        if not all(newTag.canConvert(record.value) for record in self.records[oldTag]):
            return False
        
        self.stack.beginMacro(self.tr("Change tag"))

        if newTag not in self.records.tags():
            for record in self.records[oldTag]:
                newRecord = record.copy()
                newRecord.tag = newTag
                newRecord.value = newTag.convertValue(record.value)
                self._command('changeRecord', tag=oldTag, oldRecord=record,newRecord=newRecord)
            self._command('changeTag', oldTag=oldTag, newTag=newTag)
        else:
            # Now things get complicated: We have to remove all records and add them to the existing tag.
            # Note: In rare cases it might happen that two old values are converted to the same value in the
            # new tag.
            for oldRecord in self.records[oldTag]:
                self._command('removeRecord', record=oldRecord)
                newRecord = Record(newTag, newTag.convertValue(oldRecord.value), self.elements,
                                   oldRecord.elementsWithValue)
                self._insertRecord(-1, newRecord)
            self._command('removeTag', tag=oldTag)

        self.stack.endMacro()
        return True
        
    def split(self, record, separator):
        """Split the given record using the given separator. If record.value is for example
        'Artist 1/Artist 2' and separator is '/', this method will replace *record* by two records of
        values 'Artist 1' and 'Artist 2'.
        """
        self.stack.beginMacro(self.tr("Split"))
        result = self._split(record, separator)
        self.stack.endMacro()
    
    def splitMany(self, records, separator):
        """Split each of the given records using *separator*."""
        if len(records) > 0:
            self.stack.beginMacro(self.tr("Split %n record(s)", '', len(records)))
            for record in records:
                self._split(record,separator)
            self.stack.endMacro()
        
    def _split(self, record, separator):    
        """Helper function for split and splitMany: Add commands to the stack that will split *record* at the
        given separator. Handle special cases correctly (',',  'a,a', etc.).
        This method must be called from within a macro.
        """
        assert record.tag.type in (tags.TYPE_VARCHAR,tags.TYPE_TEXT)
        # The type restriction implies that the empty string is the only possible invalid value
        splittedValues = [value for value in record.value.split(separator) if len(value) > 0]
        # Note that splittedValues might be empty (split ',')
        if splittedValues != [record.value]:
            pos = self.records[record.tag].index(record)
        
            # First remove the old value
            self._command('removeRecord', record=record)
            
            # Now create new records and insert them at pos
            for value in reversed(splittedValues):
                newRecord = record.copy()
                newRecord.value = value
                self._insertRecord(pos, newRecord)
        
    def editMany(self, records, newValues):
        """Given a list of records and an equally long lists of values, change the value of the i-th record
        to the i-th value."""
        if len(records) > 0:
            self.stack.beginMacro(self.tr("Edit %n record(s)", '', len(records)))
            for record, value in zip(records, newValues):
                if record.value != value:
                    newRecord = record.copy()
                    newRecord.value = value
                    self._changeRecord(record, newRecord)   
            self.stack.endMacro()

    def extendRecords(self,records):
        """Make the given records common, i.e. set record.elementsWithValue to all elements."""
        if len(records) > 0:
            self.stack.beginMacro(self.tr("Extend %n record(s)", '', len(records)))

            for record in records:
                if record.isCommon():
                    continue
                newRecord = record.copy()
                newRecord.elementsWithValue = self.elements
                self._command('changeRecord', tag=record.tag, oldRecord=record, newRecord=newRecord)
        
            self.stack.endMacro()
        
    def getPossibleSeparators(self, records):
        """Return all separators (from constants.SEPARATORS) that are present in every value of the given
        records. Only return separators if all records are either of type varchar or text."""
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
    
    def _handleLevelChanged(self, event):
        """React to change events of the underlying level."""
        if not isinstance(event, levels.LevelChangedEvent):
            return
        
        if len(event.removedIds) > 0 and any(element.id in event.removedIds for element in self.elements):
            self.setElements(self.level,
                             [element for element in self.elements if element.id not in event.removedIds])
            return # setElements will built records from scratch
        
        # When tags are changed via the tageditor, its internal structure is updated together with the
        # change and here is nothing to do (i.e. the following code will detect no change).
        # Thus, if a change in the tags is detected below, the tag change must originate somewhere outside
        # the tageditor.
        
        if len(event.dataIds) == 0 or not any(element.id in event.dataIds for element in self.elements):
            return # not our problem

        changed = False
        actualRecords = self._createRecords()
        for record in actualRecords[tags.TITLE]:
            print("ACTUAL", record)
        print("=====")
        for record in self.records[tags.TITLE]:
            print("CURRENT", record)
        
        for tag in self.records.tags():
            if tag not in actualRecords:
                for record in self.records[tag]:
                    self.records.removeRecord(record)
                self.records.removeTag(tag)
                changed = True
            elif len(self.records[tag]) > len(actualRecords[tag]):
                recordsToRemove = self.records[tag][len(actualRecords[tag]):]
                for record in recordsToRemove:
                    self.records.removeRecord(record)
        
        for tag in actualRecords:
            if tag not in self.records.tags():
                self.records.insertTag(len(self.records.tags()),tag)
                changed = True
            
            for i,record in enumerate(actualRecords[tag]):
                if i >= len(self.records[tag]):
                    self.records.insertRecord(i,record)
                    changed = True
                elif self.records[tag][i] != record:
                    self.records.changeRecord(tag,self.records[tag][i],record)
                    changed = True
        
        if changed:
            # After a single change to the records that is not covered by TagEditorUndoCommands, we must not
            # allow existing TagEditorUndoCommands to change the records directly.
            self.substack.reset()
            
# The following lines implement a theoretically better handling of events. Instead of building everything
# from scratch this tries to figure out which changes have been performed and tries to e.g. keep the
# position of a record whose value has changed.
#        eventIds = set(event.dataIds)
#        modified = []
#        
#        for tag in self.records.tags():
#            for record in self.records[tag]:
#                toRemove = []
#                for element in record.elementsWithValue:
#                    if tag not in element.tags or record.value not in element.tags[tag]:
#                        toRemove.append(element)
#                if len(toRemove) > 0:
#                    if len(toRemove) == len(record.elementsWithValue):
#                        record.elementsWithValue = []
#                    else:
#                        record.elementsWithValue = [el for el in record.elementsWithValue
#                                                       if el not in toRemove]
#                        if record not in modified:
#                            modified.append(record)
#                # do not remove empty records
#                
#        for element in self.elements:
#            if element.id not in eventIds:
#                continue
#            for tag in element.tags:
#                if tag not in self.records.tags():
#                    self.records.insertTag(len(self.records.tags()),tag) #TODO
#                    for i,value in enumerate(element.tags[tag]):
#                        record = Record(tag,value,self.elements,[element])
#                        self.records.insertRecord(i,record)
#                else:
#                    for value in element.tags[tag]:
#                        record = self.records.get(tag,value)
#                        if record is not None:
#                            if element not in record.elementsWithValue:
#                                record.elementsWithValue.append(element) #TODO
#                                if record not in modified:
#                                    modified.append(record)
#                        else:
#                            record = Record(tag,value,self.elements,[element])
#                            for r in self.records[tag]:
#                                if len(r.elementsWithValue) == 0:
#                                    record = r
#                                    record.value = value
#                                    record.elementsWithValue = [element]
#                                    if record not in modified:
#                                        modified.append(record)
#                                    break
#                            else:
#                                record = Record(tag,value,self.elements,[element])
#                                self.records.insertRecord(len(self.records[tag]),record)
#                            
#        for tag in self.records.tags():
#            toRemove = [record for record in self.records[tag] if len(record.elementsWithValue) == 0]
#            for record in toRemove:
#                self.records.removeRecord(record)
#                
#        for record in modified:
#            self.records.changeRecord(tag,record,record) #TODO
#                    