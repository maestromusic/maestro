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

import collections, datetime, math

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt
translate = QtCore.QCoreApplication.translate

from ... import database as db
from ...core import tags, elements
from ...gui import mainwindow

try:
    import matplotlib.pyplot as pyplot
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg
except ImportError as e:
    pyplot = None
    pyplotError = str(e)


def enable():
    mainwindow.addWidgetData(mainwindow.WidgetData(
        id = "statistics",
        name = QtGui.QApplication.translate("Statistics", "Statistics"),
        theClass = StatisticsWidget,
        icon = QtGui.QIcon(":/omg/plugins/statistics/statistics.png")
        ))


def disable():
    mainwindow.removeWidgetData("statistics")
    

class StatisticsWidget(QtGui.QWidget):
    """Widget that displays some statistics (or an error message if matplotlib cannot be loaded)."""
    def __init__(self, state=None):
        super().__init__()
        if pyplot is None:
            layout = QtGui.QHBoxLayout(self)
            errorLabel = QtGui.QLabel(pyplotError)
            errorLabel.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            layout.addWidget(errorLabel)
            return
        
        self.setLayout(QtGui.QHBoxLayout())
        scroll = QtGui.QScrollArea()
        self.layout().addWidget(scroll)
        innerWidget = QtGui.QWidget()
        self.innerLayout = QtGui.QGridLayout(innerWidget)
        if tags.get("genre").isInDb() and tags.get("genre").type == tags.TYPE_VARCHAR:
            sizes, labels = self._filter(self.getGenres())
            self._addPie(self.tr("Genres"), 0, 0, sizes, labels, 4, 3)
            sizes, labels = self._filter(self.getFormats())
            self._addPie(self.tr("Formats"), 0, 1, sizes, labels, 3.2, 3)
            sizes, labels = self._filter(self.getContainerTypes())
            self._addPie(self.tr("Container types"), 1, 1, sizes, labels, 3.2, 3)
            
            heights, labels = zip(*self.getDates())
            self._addBars(self.tr("Dates"), 1, 0, heights, labels, 4, 4)
            
        scroll.setWidget(innerWidget)
    
    def _addPie(self, title, row, column, sizes, labels, width, height):
        """Add a bar chart at position (row, column) to the layout."""
        if len(sizes) == 0:
            return
        figure = Figure([width, height], facecolor="white")
        colors = ['yellowgreen', 'gold', 'lightskyblue', 'lightcoral']
        ax = figure.gca(aspect="equal")
        ax.pie(sizes, shadow=True, colors=colors, labels=labels,
               autopct=lambda p: "{} %".format(round(p)) if p >= 8 else '')
        canvas = FigureCanvasQTAgg(figure)
        self.innerLayout.addWidget(QtGui.QLabel(title), 2*row, column)
        self.innerLayout.addWidget(canvas, 2*row+1, column)
        
    def _addBars(self, title, row, column, heights, labels, width, height):
        """Add a bar plot at position (row, column) to the layout."""
        if len(heights) == 0:
            return
        figure = Figure([width, height], facecolor="white")
        ax = figure.add_axes([0.125,0.25,0.8,0.7])
        ax.bar(range(len(heights)), heights)
        ax.set_xticks(range(len(heights)))
        ax.set_xticklabels(labels, rotation=70)
        canvas = FigureCanvasQTAgg(figure)
        self.innerLayout.addWidget(QtGui.QLabel(title), 2*row, column)
        self.innerLayout.addWidget(canvas, 2*row+1, column)
        
    def _filter(self, tuples, number=6, p1=0.01, p2=0.05):
        """Given a list of (size, label)-tuples for wedges in a pie chart, merge the smaller wedges to
        an "Other"-wedge.
        The input list must be sorted in descending order!
        In detail: The filter will keep all wedges whose percentage is >= *p2* and also those whose
        percentage is >= *p1* as long as the total number is <= *number*.
        """
        s = sum(t[0] for t in tuples)
        if s == 0:
            return []
        p1 *= s
        p2 *= s
        i = 0
        while i < len(tuples):
            p = tuples[i][0]
            if p >= p2 or (p >= p1 and i < number):
                i += 1
            else: break
        if i < len(tuples):
            tuples = tuples[:i]
            tuples.append((s-sum(t[0] for t in tuples), self.tr("Other")))
        return zip(*tuples)
        
    def getGenres(self):
        """Return sizes and labels for each wedge in the genre chart. The percentage of a wedge
        is its size divided by the sum of all sizes times 100."""
        tag = tags.get("genre")
        if not tag.isInDb() or tag.type != tags.TYPE_VARCHAR:
            return []
        result = db.query("""
            SELECT COUNT(*) AS count, v.value
            FROM {p}tags AS t
                JOIN {p}elements AS el ON t.element_id = el.id
                JOIN {p}values_varchar AS v ON t.tag_id=v.tag_id AND t.value_id = v.id
            WHERE el.file = 1 AND t.tag_id=?
            GROUP BY value_id
            ORDER BY count DESC
            """, tag.id)
        return list(result)
    
    def getFormats(self):
        """Return sizes and labels for each wedge in the file format chart. The percentage of a wedge
        is its size divided by the sum of all sizes times 100."""
        types = collections.defaultdict(int)
        result = db.query('SELECT url FROM {p}files').getSingleColumn()
        for url in result:
            pos = url.find('://')
            if pos != -1:
                scheme = url[:pos+3]
                if scheme == 'file://':
                    pos = url.rfind('.') 
                    if pos != -1:
                        types[url[pos+1:]] += 1
                    else: types['file://'] += 1
                else: types[scheme] += 1
            else: types['<None>'] += 1
                
        types = [(c, t) for t, c in types.items()]
        types.sort(reverse=True)
        return types
    
    def getContainerTypes(self):
        """Return sizes and labels for each wedge in the container types chart. The percentage of a wedge
        is its size divided by the sum of all sizes times 100."""
        result = db.query("""
            SELECT COUNT(*) AS count, type
            FROM {p}elements
            WHERE file = 0
            GROUP BY type
            ORDER BY count DESC
            """)
        return [(row[0], elements.getTypeTitle(row[1])) for row in result]
    
    def getDates(self):
        """Return heights and labels of the bars in the date chart."""
        result = db.query("""
            SELECT v.value DIV 10000 AS date, COUNT(*) AS count 
            FROM new_tags AS t JOIN new_values_date AS v ON t.tag_id = v.tag_id AND t.value_id = v.id
            WHERE t.tag_id = 8
            GROUP BY date
            """)
        counters = collections.defaultdict(int)
        for date, count in result:
            if date < 1700:
                date = (date // 100) * 100
            elif date < 1950:
                date = (date // 50) * 50
            else:
                date = (date // 10) * 10
            counters[date] += count
            
        def dateToStr(date):
            if date < 1700:
                return "{}-{}".format(date, date+99)
            elif date < 1950:
                return "{}-{}".format(date, date+49)
            elif date < 2000: #70s etc.
                return "{}s".format(date % 100)
            else: return "{}-{}".format(date, min(date+9, datetime.date.today().year))
            
        return [(counters[date], dateToStr(date)) for date in sorted(counters.keys())]
