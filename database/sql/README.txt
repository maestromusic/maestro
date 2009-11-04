This module contains an abstraction layer for SQL databases. It provides a common API to several third party SQL modules so that the actual SQL module can be exchanged without changing the project code.

Currently the following drivers are supported:
"mypysql": uses the mysql-python module (http://sourceforge.net/projects/mypysql/)
"qtsql": uses the QtSql-Module of PyQt4 (http://doc.trolltech.com/4.2/qtsql.html)


Usage of the module:
=====================================
import sql

db = sql. newConnection(drivername)    # use the driver's string identifier above

result = db.query("SELECT name,country FROM persons WHERE id = ?",person)   # Use ? as placeholder to insert parameters which are automatically escaped

# When using query, this iterator yields for each person a tuple with the corresponding data.
for row in result:
  print(row[0])  #  e.g. ("Max Mustermann","Germany")

# Another way is to use queryDict. The iterator will then return a dictionary {columnname => data} for each person
result = db.queryDict("SELECT name,country FROM persons WHERE id = ?",person)

for row in result:
  print(row[0])  #  e.g. {"name": "Max Mustermann","country": "Germany"}

# An easy method to retrieve a single value from the database is getSingle:
number = db.query("SELECT COUNT(*) FROM persons").getSingle()


Package-global method:
====================================
newConnection(driver): Creates a new database connection object (instance of Sql) using the given driver identifier. It does not open the connection.


Classes
====================================
class DBException: Class for database-related exceptions in this package.


class Sql:
    This class encapsulates a connection to a database. To create instances of Sql use newConnection.
    
    connect(self,username,password,database,host="localhost",port=3306)
        Connects to the database with the given information. Raises a DBException if that doesn't work.

    query(self,queryString,*args)
        Executes the query queryString and returns an SqlResult object which yields the result's rows in tuples. The queryString may contain ? as placeholders which are replaced by the args-parameters in the given order. Before replacing the args-parameters are escaped. Escaping is done by the driver and may vary...but the following works with all drivers:
        query("SELECT ? FROM ? WHERE id=?",columnname,tablename,id).
        
   queryDict(self,queryString,*args)
       Executes the query queryString and returns an SqlResult object which yields the result's rows in dictionaries. Placeholders may be used (confer query).

class SqlResult:
    This class encapsulates the result of the execution of an SQL query. It may contain selected rows from the database or information like the number of affected rows. SqlResult implements __iter__ so it may be used in for loops to retrieve all rows from the result set. Depending on whether query or queryDict was used to create this SqlResult-instance the rows are returned as tuple or as dictionary. In the latter case the column-names are used as keys unless the query specified an alias. A short way to retrieve a single value from the database is getSingle But be careful not to mix getSingle and iterator methods (e.g. next) since both may change internal cursors and could interfere with each other.

    size(self)
        Returns the number of rows selected in a select query. You can also use the built-in len-method.

    def next(self):
        Yields the next row from the result set or raises a StopIteration if there is no such row.

    def executedQuery(self):
        Returns the query which was executed. Depending on the driver placeholders may be replaced by the inserted values. This method is mainly for debugging.

    def affectedRows(self):
        Returns the number of rows which were affected by a query like UPDATE.

    def insertId(self):
        Retrieves the ID generated for an AUTO_INCREMENT column by the previous INSERT query.

    def getSingle(self):
        Returns the first value from the first row of the result set and should be used as a shorthand method if the result contains only one value. Do not use this method together with iterators as both of them may move the internal cursor.

        
Driver modules
====================================
Driver modules must be named <driverIdentifier>.py to ensure that the package can load them. Each module must contain a class Sql.
