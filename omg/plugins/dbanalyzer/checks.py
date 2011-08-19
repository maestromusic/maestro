# -*- coding: utf-8 -*-
# Copyright 2011 Martin Altmayer
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation
#

from PyQt4 import QtGui
translate = QtGui.QApplication.translate

from omg import database as db, tags


class Check:
    """Abstract base class for checks. A check tests the database for one consistency criterion and returns the number of errors or even detail information (e.g. the ids of the affected rows). Both the number and the data will be cached. Finally a check can even (try to) fix the problems."""
    def __init__(self):
        self.number = None
        self.data = None

    def getName(self):
        """Return a displayable name of this check."""
        return self._name

    def getInfo(self):
        """Return a description of this check for the user."""
        return self.__class__.__doc__

    def getNumber(self,refresh = False):
        """Return the number of errors in the database and cache it. Return the cached value unless *refresh* is true."""
        if refresh or self.number is None:
            self.number = self.check(data=False)
        return self.number

    def getData(self,refresh = False):
        """Return detail data to errors in the database and cache it. Return the cached data unless *refresh* is true. The result is a list of tuples where each tuple contains information to a single error. The meaning of the tuple entries is returned by :meth:`getColumnHeaders`."""
        if refresh or self.data is None:
            self.data = self.check(data=True)
        return self.data

    def getColumnHeaders(self):
        """Return column headers for the data returned by :meth:`getData`."""
        return self._columnHeaders
    
    def fix(self):
        """Fix the problem and delete cached data. After this method :meth:`getNumber` should return ''0''."""
        if self.getNumber() > 0:
            self._fix()
        self.number = None
        self.data = None


class ElementCounterCheck(Check):
    """Check for broken element counters in the element table."""
    _columnHeaders = (translate("DBAnalyzerChecks","ID"),translate("DBAnalyzerChecks","Name"),
                     translate("DBAnalyzerChecks","In DB"),translate("DBAnalyzerChecks","Real"))

    _name = translate("DBAnalyzerChecks","Element counter")
    
    def check(self,data):
        if not data:
            return db.query("""
                SELECT COUNT(*) FROM {0}elements
                WHERE elements !=
                    (SELECT COUNT(*) FROM {0}contents
                     WHERE container_id = id)
                """.format(db.prefix)).getSingle()
        else:
            result = db.query("""
                SELECT id,elements,COUNT(element_id) AS realelements
                FROM {0}elements LEFT JOIN {0}contents ON container_id = id
                GROUP BY id
                HAVING realelements != elements
                """.format(db.prefix))
            return [(row[0],getTitle(row[0]),row[1],row[2]) for row in result]

    def _fix(self):
        db.write.updateElementsCounter()


class ToplevelFlagCheck(Check):
    """Check for broken toplevel flags in the elements table. The toplevel flag should be true if and only if the element does not appear as a child in the contents table."""
    _columnHeaders = (translate("DBAnalyzerChecks","ID"),translate("DBAnalyzerChecks","Name"),
                     translate("DBAnalyzerChecks","In DB"),translate("DBAnalyzerChecks","Real"))
                     
    _name = translate("DBAnalyzerChecks","Toplevel flags")

    def check(self,data):
        if not data:
            return db.query("""
                    SELECT COUNT(*) FROM {0}elements
                    WHERE toplevel != (NOT id IN (SELECT element_id FROM {0}contents))
                    """.format(db.prefix)).getSingle()
        else:
            result = db.query("""
                    SELECT id,toplevel FROM {0}elements
                    WHERE toplevel != (NOT id IN (SELECT element_id FROM {0}contents))
                    """.format(db.prefix))
            return [(row[0],getTitle(row[0]),row[1],(row[1] + 1) % 2) for row in result]

    def _fix(self):
        db.write.updateToplevelFlags()
            

class FileFlagCheck(Check):
    """Check for broken file flags in the element table. The file flag should be true if and only if the element is contained in the file table."""
    _columnHeaders = (translate("DBAnalyzerChecks","ID"),translate("DBAnalyzerChecks","Name"),
                     translate("DBAnalyzerChecks","In DB"),translate("DBAnalyzerChecks","Real"))
                     
    _name = translate("DBAnalyzerChecks","File flags")
    
    def check(self,data):
        if not data:
            return db.query("""
                SELECT COUNT(*) FROM {0}elements LEFT JOIN {0}files ON id = element_id
                WHERE (file != 0) != (element_id IS NOT NULL)
                """.format(db.prefix)).getSingle()
        else:
            result = db.query("""
                SELECT id,file FROM {0}elements LEFT JOIN {0}files ON id = element_id
                WHERE (file != 0) != (element_id IS NOT NULL)
                """.format(db.prefix))
            return [(row[0],getTitle(row[0]),row[1],(row[1] + 1) % 2) for row in result]

    def _fix(self):
        db.query("""
            UPDATE {0}elements LEFT JOIN {0}files ON id = element_id
            SET file = (element_id IS NOT NULL)
            """.format(db.prefix))


class EmptyContainerCheck(Check):
    """Check for empty containers in the elements table. This check uses the file table and not elements.elements. Fixing this check will set the file flag to true if the element is contained in the files table. Otherwise it will be deleted. Warning: Actually empty containers do not make the database corrupt. Especially during editing containers may be empty on purpose."""
    _columnHeaders = (translate("DBAnalyzerChecks","ID"),translate("DBAnalyzerChecks","Name"),
                      translate("DBAnalyzerChecks","Element Counter"),translate("DBAnalyzerChecks","File (in file table)"))
                     
    _name = translate("DBAnalyzerChecks","Empty containers")
    
    def check(self,data):
        if not data:
            return db.query("""
                SELECT COUNT(*) FROM {0}elements LEFT JOIN {0}contents ON id = container_id
                WHERE file = 0 AND container_id IS NULL
                """.format(db.prefix)).getSingle()
        else:
            result = db.query("""
                SELECT id,elements,({0}files.element_id IS NOT NULL)
                FROM {0}elements LEFT JOIN {0}contents ON id = container_id
                                 LEFT JOIN {0}files ON id = {0}files.element_id
                WHERE file = 0 AND container_id IS NULL
                """.format(db.prefix))
            return [(row[0],getTitle(row[0]),row[1],row[2]) for row in result]

    def _fix(self):
        db.query("""
                UPDATE {0}elements LEFT JOIN {0}contents ON id = container_id
                                   LEFT JOIN {0}files ON id = {0}files.element_id
                SET file = 1
                WHERE file = 0 AND container_id IS NULL AND {0}files.element_id IS NOT NULL
                """.format(db.prefix))
        db.query("""
                DELETE {0}elements FROM {0}elements LEFT JOIN {0}contents ON id = container_id
                WHERE file = 0 AND container_id IS NULL
                """.format(db.prefix))


class SuperfluousTagValuesCheck(Check):
    """Check for tag values which are not referenced by any element."""
    _columnHeaders = (translate("DBAnalyzerChecks","Value type"),translate("DBAnalyzerChecks","Tag ID"),
                      translate("DBAnalyzerChecks","ID"),translate("DBAnalyzerChecks","Value"))
                     
    _name = translate("DBAnalyzerChecks","Superfluous tag values")

    def _query(self,type,data,delete):
        """Build a query selecting superfluous tags values of value type *type* (or only their number if *data* is false)."""
        if not delete:
            if not data:
                beginning = "SELECT COUNT(*)"
            else: beginning = "SELECT {0}values_{1}.tag_id,id,value".format(db.prefix,type)
        else: beginning = "DELETE {0}values_{1}".format(db.prefix,type)
        return beginning + """
            FROM {0}values_{1} LEFT JOIN {0}tags ON {0}values_{1}.tag_id = {0}tags.tag_id
                                                AND {0}values_{1}.id = {0}tags.value_id
            WHERE element_id IS NULL
            """.format(db.prefix,type)
            
    def check(self,data):
        if not data:
            return sum(db.query(self._query(type.name,False,False)).getSingle() for type in tags.TYPES)
        else:
            result = []
            for type in tags.TYPES:
                result.extend((type.name,row[0],row[1],row[2]) for row in db.query(self._query(type.name,True,False)))
            return result

    def _fix(self):
        for type in tags.TYPES:
            db.query(self._query(type.name,False,True))


class ValueIdsCheck(Check):
    """Check for entries in the tag table that reference a tag id which does not exist in the corresponding tag table."""
    _columnHeaders = (translate("DBAnalyzerChecks","ID"),translate("DBAnalyzerChecks","Name"),
                      translate("DBAnalyzerChecks","Tag ID"),translate("DBAnalyzerChecks","Value ID"))
                      
    _name = translate("DBAnalyzerChecks","Value IDs")

    def _query(self,type,data,delete):
        """Build a query selecting invalid tag references in the tag-table of type *type* (or only their number if *data* is true)."""
        if not delete:
            if not data:
                beginning = "SELECT COUNT(*)"
            else: beginning = "SELECT element_id,{0}tags.tag_id,value_id".format(db.prefix)
        else: beginning = "DELETE {0}tags".format(db.prefix)
        return beginning + """
            FROM {0}tags LEFT JOIN {0}values_{1} ON {0}tags.tag_id = {0}values_{1}.tag_id
                                                 AND {0}tags.value_id = {0}values_{1}.id
                  WHERE {0}tags.tag_id IN (SELECT id FROM {0}tagids WHERE tagtype = '{1}') AND id IS NULL
            """.format(db.prefix,type)
            
    def check(self,data):
        if not data:
            return sum(db.query(self._query(type.name,False,False)).getSingle() for type in tags.TYPES)
        else:
            result = []
            for type in tags.TYPES:
                result.extend((row[0],getTitle(row[0]),row[1],row[2])
                                    for row in db.query(self._query(type.name,True,False)))
            return result
            
    def _fix(self):
        for type in tags.TYPES:
            db.query(self._query(type.name,False,True))


def getTitle(id):
    """Return a displayable title for the element with the given id."""
    titles = list(db.query("""
            SELECT value FROM {0}values_{1}
            WHERE id IN (SELECT value_id FROM {0}tags WHERE element_id = ? AND tag_id = ?)
            """.format(db.prefix,tags.TITLE.type.name),id,tags.TITLE.id).getSingleColumn())
    if len(titles) > 0:
        return " - ".join(titles)
    else: return translate("DBAnalyzerChecks","<No title>")
