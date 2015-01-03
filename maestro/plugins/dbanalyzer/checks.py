# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2015 Martin Altmayer, Michael Helmling
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

from PyQt4 import QtCore

from ... import config, database as db, utils
from ...core import tags

translate = QtCore.QCoreApplication.translate


class Check:
    """Abstract base class for checks. A check tests the database for one consistency criterion and returns
    the number of errors or even detail information (e.g. the ids of the affected rows). Both the number and
    the data will be cached. Finally a check can even (try to) fix the problems.
    """
    def __init__(self):
        self.number = None
        self.data = None

    def getName(self):
        """Return a displayable name of this check."""
        return self._name

    def getInfo(self):
        """Return a description of this check for the user."""
        return self.__class__.__doc__

    def getNumber(self, refresh=False):
        """Return the number of errors in the database and cache it. Return the cached value unless
        *refresh* is true."""
        if refresh or self.number is None:
            self.number = self.check(data=False)
        return self.number

    def getData(self, refresh=False):
        """Return detail data to errors in the database and cache it. Return the cached data unless
        *refresh* is true. The result is a list of tuples where each tuple contains information to a single
        error. The meaning of the tuple entries is returned by :meth:`getColumnHeaders`.
        """
        if refresh or self.data is None:
            self.data = self.check(data=True)
        return self.data

    def getColumnHeaders(self):
        """Return column headers for the data returned by :meth:`getData`."""
        return self._columnHeaders
    
    def fix(self):
        """Fix the problem and delete cached data. After this method :meth:`getNumber` should return 0."""
        if self.getNumber() > 0:
            self._fix()
        self.number = None
        self.data = None


class ElementCounterCheck(Check):
    """Check for broken element counters in the element table."""
    _columnHeaders = (translate("DBAnalyzerChecks", "ID"), translate("DBAnalyzerChecks", "Name"),
                     translate("DBAnalyzerChecks", "In DB"), translate("DBAnalyzerChecks", "Real"))

    _name = translate("DBAnalyzerChecks", "Element counter")
    
    def check(self, data):
        if not data:
            return db.query("""
                SELECT COUNT(*) FROM {p}elements
                WHERE elements !=
                    (SELECT COUNT(*) FROM {p}contents
                     WHERE container_id = id)
                """).getSingle()
        else:
            result = db.query("""
                SELECT id, elements, COUNT(element_id) AS realelements
                FROM {p}elements LEFT JOIN {p}contents ON container_id = id
                GROUP BY id
                HAVING realelements != elements
                """)
            return [(row[0], getTitle(row[0]), row[1], row[2]) for row in result]

    def _fix(self):
        db.updateElementsCounter()
            

class FileFlagCheck(Check):
    """Check for broken file flags in the element table. The file flag should be true if and only if the
    element is contained in the file table."""
    _columnHeaders = (translate("DBAnalyzerChecks", "ID"), translate("DBAnalyzerChecks", "Name"),
                     translate("DBAnalyzerChecks", "In DB"), translate("DBAnalyzerChecks", "Real"))
                     
    _name = translate("DBAnalyzerChecks", "File flags")
    
    def check(self, data):
        if not data:
            return db.query("""
                SELECT COUNT(*) FROM {p}elements LEFT JOIN {p}files ON id = element_id
                WHERE (file != 0) != (element_id IS NOT NULL)
                """).getSingle()
        else:
            result = db.query("""
                SELECT id, file FROM {p}elements LEFT JOIN {p}files ON id = element_id
                WHERE (file != 0) != (element_id IS NOT NULL)
                """)
            return [(row[0], getTitle(row[0]), row[1], (row[1] + 1) % 2) for row in result]

    def _fix(self):
        db.query("""
            UPDATE {p}elements LEFT JOIN {p}files ON id = element_id
            SET file = (element_id IS NOT NULL)
            """)


class EmptyContainerCheck(Check):
    """Check for empty containers in the elements table. This check uses the file table and not
    elements.elements. Fixing this check will set the file flag to true if the element is contained in the
    files table. Otherwise it will be deleted. Warning: Actually empty containers do not make the database
    corrupt. Especially during editing containers may be empty on purpose.
    """
    _columnHeaders = (translate("DBAnalyzerChecks", "ID"),
                      translate("DBAnalyzerChecks", "Name"),
                      translate("DBAnalyzerChecks", "Element Counter"),
                      translate("DBAnalyzerChecks", "File (in file table)"))
                     
    _name = translate("DBAnalyzerChecks", "Empty containers")
    
    def check(self, data):
        if not data:
            return db.query("""
                SELECT COUNT(*) FROM {p}elements LEFT JOIN {p}contents ON id = container_id
                WHERE file = 0 AND container_id IS NULL
                """).getSingle()
        else:
            result = db.query("""
                SELECT id, elements, ({p}files.element_id IS NOT NULL)
                FROM {p}elements LEFT JOIN {p}contents ON id = container_id
                                 LEFT JOIN {p}files ON id = {p}files.element_id
                WHERE file = 0 AND container_id IS NULL
                """)
            return [(row[0], getTitle(row[0]), row[1], row[2]) for row in result]

    def _fix(self):
        # Set file=1 for empty containers which appear in the files-table
        with db.transaction():
            # Note: SQLite does not support JOIN in UPDATE or DELETE queries.
            ids = list(db.query("""
                    SELECT id
                    FROM {p}elements LEFT JOIN {p}contents ON id = container_id
                                     LEFT JOIN {p}files ON id = {p}files.element_id
                    WHERE file = 0 AND container_id IS NULL AND {p}files.element_id IS NOT NULL
                    """))
            if len(ids):
                db.multiQuery("UPDATE {p}elements SET file=1 WHERE id=?", ids)
                
            # Delete remaining empty containers
            ids = list(db.query("""
                    SELECT id
                    FROM {p}elements LEFT JOIN {p}contents ON id = container_id
                    WHERE file = 0 AND container_id IS NULL
                    """))
            if len(ids):
                db.multiQuery("DELETE FROM {p}elements WHERE id=?", ids)


class SuperfluousTagValuesCheck(Check):
    """Check for tag values which are not referenced by any element."""
    _columnHeaders = (translate("DBAnalyzerChecks", "Value type"), translate("DBAnalyzerChecks", "Tag ID"),
                      translate("DBAnalyzerChecks", "ID"), translate("DBAnalyzerChecks", "Value"))
                     
    _name = translate("DBAnalyzerChecks", "Superfluous tag values")

    def _query(self, type, data, delete):
        """Build a query selecting superfluous tag values of value-type *type* (or only their number if
        *data* is false). If *delete* is True, return a query """
        tableName = "{}values_{}".format(db.prefix, type)
        # This is complicated because we need different queries for MySQL and SQLite.
        # Neither query works in both.
        mainPart = """ FROM {1} LEFT JOIN {0}tags ON {1}.tag_id = {0}tags.tag_id
                                                 AND {1}.id = {0}tags.value_id
                    WHERE element_id IS NULL
                    """.format(db.prefix, tableName)
        if not delete:
            if not data:
                return "SELECT COUNT(*)" + mainPart
            else: return "SELECT {}.tag_id, id, value {}".format(tableName, mainPart)
        else:
            if config.options.database.type == 'mysql':
                # Cannot use DELETE together with JOIN in SQLite
                return "DELETE {} {}".format(tableName, mainPart)
            else:
                # Cannot delete from a table used in a subquery in MySQL
                return "DELETE FROM {0} WHERE id IN (SELECT {0}.id {1})".format(tableName, mainPart)
            
    def check(self, data):
        if not data:
            return sum(db.query(self._query(type.name, False, False)).getSingle() for type in tags.TYPES)
        else:
            result = []
            for type in tags.TYPES:
                result.extend((type.name, row[0], row[1], row[2])
                              for row in db.query(self._query(type.name, True, False)))
            return result

    def _fix(self):
        for type in tags.TYPES:
            db.query(self._query(type.name, False, True))


class ValueIdsCheck(Check):
    """Check for entries in the tag table that reference a tag id which does not exist in the corresponding
    tag table."""
    _columnHeaders = (translate("DBAnalyzerChecks", "ID"), translate("DBAnalyzerChecks", "Name"),
                      translate("DBAnalyzerChecks", "Tag ID"), translate("DBAnalyzerChecks", "Value ID"))
                      
    _name = translate("DBAnalyzerChecks", "Value IDs")

    def _query(self, type, data, delete):
        """Build a query selecting invalid tag references in the tag-table of type *type* (or only their
        number if *data* is true)."""
        if not delete:
            if not data:
                beginning = "SELECT COUNT(*)"
            else: beginning = "SELECT element_id, {0}tags.tag_id, value_id".format(db.prefix)
        else: beginning = "DELETE {0}tags".format(db.prefix)
        return beginning + """
            FROM {0}tags LEFT JOIN {0}values_{1} ON {0}tags.tag_id = {0}values_{1}.tag_id
                                                 AND {0}tags.value_id = {0}values_{1}.id
                  WHERE {0}tags.tag_id IN (SELECT id FROM {0}tagids WHERE tagtype = '{1}') AND id IS NULL
            """.format(db.prefix, type)
            
    def check(self, data):
        if not data:
            return sum(db.query(self._query(type.name, False, False)).getSingle() for type in tags.TYPES)
        else:
            result = []
            for type in tags.TYPES:
                result.extend((row[0], getTitle(row[0]), row[1], row[2])
                                    for row in db.query(self._query(type.name, True, False)))
            return result
            
    def _fix(self):
        for type in tags.TYPES:
            db.query(self._query(type.name, False, True))


class DoubleTagsCheck(Check):
    """Check for tag-relations that appear twice in the database.""" 
    _columnHeaders = (translate("DBAnalyzerChecks", "ID"), translate("DBAnalyzerChecks", "Name"),
                      translate("DBAnalyzerChecks", "Tag ID"), translate("DBAnalyzerChecks", "Value ID"),
                      translate("DBAnalyzerChecks", "Value"))

    _name = translate("DBAnalyzerChecks", "Double tags")
    
    def check(self, data):
        result = list(db.query("""
            SELECT element_id, tag_id, value_id
            FROM {p}tags
            GROUP BY element_id, tag_id, value_id
            HAVING COUNT(*) > 1
            """))
        if not data:
            return len(result)
        else:
            return [(row[0], getTitle(row[0]), row[1], row[2], str(db.valueFromId(row[1], row[2])))
                    for row in result]

    def _fix(self):
        result = db.query("""
            SELECT element_id, tag_id, value_id
            FROM {p}tags
            GROUP BY element_id, tag_id, value_id
            HAVING COUNT(*) > 1
            """)
        values = list(result)
        with db.transaction():
            db.multiQuery("DELETE FROM {p}tags WHERE element_id=? AND tag_id=? AND value_id=?", values)
            db.multiQuery("INSERT INTO {p}tags (element_id, tag_id, value_id) VALUES (?,?,?)", values)


class WithoutTagsCheck(Check):
    """Check for elements without tags. WARNING: Fixing this means removing those elements from the
    database!"""
    _columnHeaders = (translate("DBAnalyzerChecks", "ID"), translate("DBAnalyzerChecks", "URL"),
                      translate("DBAnalyzerChecks", "Elements"))
                      
    _name = translate("DBAnalyzerChecks", "Without Tags")
    
    def _query(self, command):
        return """
            {0}
            FROM {1}elements AS el LEFT JOIN {1}tags AS t ON el.id = t.element_id
                                   LEFT JOIN {1}files AS f ON el.id = f.element_id
            WHERE t.tag_id IS NULL
            """.format(command, db.prefix)
            
    def check(self, data):
        if not data:
            query = self._query('SELECT COUNT(*)')
            return db.query(query).getSingle()
        else:
            query = self._query('SELECT el.id, f.url, el.elements')
            return [row for row in db.query(query)]
        
    def fix(self):
        # el is an alias for elements defined in the query's FROM-part (see above)
        db.query(self._query('DELETE el'.format(db.prefix)))
        

class DoubledFilesCheck(Check):
    """Check for files that appear twice in the database. This check currently cannot be fixed automatically.
    """
    _columnHeaders = (translate("DBAnalyzerChecks", "ID 1"), translate("DBAnalyzerChecks", "ID 2"),
                      translate("DBAnalyzerChecks", "Title"),
                      translate("DBAnalyzerChecks", "URL"))
    
    _name = translate("DBAnalyzerChecks", "Doubled files")
    
    def check(self, data):
        if not data:
            return db.query("""
                    SELECT COUNT(DISTINCT f1.element_id)
                    FROM {p}files AS f1 JOIN {p}files AS f2
                                            ON f1.url = f2.url AND f1.element_id != f2.element_id
                    """).getSingle()
        else:
            return [(row[0], row[1], getTitle(row[1]), row[2]) for row in db.query("""
                    SELECT f1.element_id, f2.element_id, f1.url
                    FROM {p}files AS f1 JOIN {p}files AS f2
                                            ON f1.url = f2.url AND f1.element_id != f2.element_id
                    """)]
        
    def fix(self): pass
    

class SearchValuesCheck(Check):
    """Check for entries in values_varchar with incorrect search_value. The search_value is used in
    diacritics-insensitive searches and should contain the normal value with all diacritics removed.
    """
    _name = translate("DBAnalyzerChecks", "Search Values")
    _columnHeaders = (translate("DBAnalyzerChecks", "ID"),
                      translate("DBAnalyzerChecks", "Value"),
                      translate("DBAnalyzerChecks", "Search value"))
    
    def check(self, data, fixData=False):
        result = db.query("SELECT id, value, search_value FROM {p}values_varchar")
        tuples = []
        counter = 0
        for id, value, searchValue in result:
            if db.isNull(searchValue):
                searchValue = None
            correct = utils.strings.removeDiacritics(value)
            if correct == value:
                correct = None
            if correct != searchValue:
                if data:
                    if not fixData:
                        tuples.append((id, value, searchValue))
                    else: tuples.append((correct, id))
                else: counter += 1
        if data:
            return tuples
        else: return counter
        
    def fix(self):
        data = self.check(True, True)
        if len(data):
            db.multiQuery("UPDATE {p}values_varchar SET search_value = ? WHERE id = ?", data)

        
def getTitle(id):
    """Return a displayable title for the element with the given id."""
    titles = list(db.query("""
            SELECT value FROM {0}values_{1}
            WHERE id IN (SELECT value_id FROM {0}tags WHERE element_id = ? AND tag_id = ?)
            """.format(db.prefix, tags.TITLE.type.name), id, tags.TITLE.id).getSingleColumn())
    if len(titles) > 0:
        return " - ".join(titles)
    else: return translate("DBAnalyzerChecks", "<No title>")
