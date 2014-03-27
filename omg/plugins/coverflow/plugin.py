# -*- coding: utf-8 -*-
# OMG Music Manager  -  http://omg.mathematik.uni-kl.de
# Copyright (C) 2009-2014 Martin Altmayer, Michael Helmling
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
import math, functools

from PyQt4 import QtCore, QtGui
from PyQt4.QtCore import Qt
translate = QtCore.QCoreApplication.translate

if __name__ != "__main__":
    from ...core import covers, levels, nodes
    from ...gui import coverbrowser, playlist, selection


# Possible values for the 'curve' option along with user friendly titles
CURVES = [
    (translate("CoverFlow", "Arc"),     "arc"),
    (translate("CoverFlow", "V-Shape"), "v"),
    (translate("CoverFlow", "Cosine"),  "cos"),
    (translate("CoverFlow", "Peak"),    "peak"),
    (translate("CoverFlow", "Gallery"), "gallery"),
]

# Colors from which the user can choose in the configuration widget.
COLORS = [
    (translate("CoverFlow", "Black"),      QtGui.QColor(0,0,0)),
    (translate("CoverFlow", "Dark gray"),  QtGui.QColor(0x40, 0x40, 0x40)),
    (translate("CoverFlow", "Light gray"), QtGui.QColor(0x80, 0x80, 0x80)),
    (translate("CoverFlow", "White"),      QtGui.QColor(0xFF, 0xFF, 0xFF)),
]

def enable(): 
    coverbrowser.addDisplayClass('coverflow', CoverFlowWidget)

def disable():
    coverbrowser.removeDisplayClass('coverflow')
    

class Cover:
    """A Cover object stores information about a cover used in the cover flow: the path, the full-size
    pixmap and a cache which contains the pixmap (resized CoverFlow.option('size')) and the reflection
    (if enabled). Pixmaps are only loaded when first requested.
    """
    def __init__(self, elid, path):
        self.elid = elid
        self.path = path
        self.pixmap = None
        self._cache = None
        
    def load(self):
        """Load the cover's pixmap."""
        if __name__ != "__main__":
            self.pixmap = covers.get(self.path)
        else:
            self.pixmap = QtGui.QPixmap(self.path)
       
    def cache(self, options):
        """Return the cached version of this cover. *options* is the set of options
        returned by CoverFlow.options."""
        if self.pixmap is None:
            self.load()
        if self._cache is None:
            self._createCache(options)
        return self._cache
      
    def _createCache(self, options):
        """Create the cached version of this cover using the specified options (from CoverFlow.options).
        The cache version contains the resized cover together with its reflection."""
        w = options['size'].width()
        h = options['size'].height()
        if options['reflection']:
            hRefl = int(h * options['reflectionFactor'])
        else: hRefl = 0
        self._cache = QtGui.QPixmap(w, h + hRefl)
        painter = QtGui.QPainter(self._cache)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        painter.drawPixmap(QtCore.QRect(0, 0, w, h), self.pixmap)
        
        if options['reflection']:
            painter.setTransform(QtGui.QTransform(1, 0, 0, -1, 0, 0)) # draw reflection upside down
            source = QtCore.QRect(0, h-hRefl, w, hRefl)
            target = QtCore.QRect(0, -h-hRefl, w, hRefl)
            painter.drawPixmap(target, self._cache, source)
            painter.resetTransform()
            
            gradient = QtGui.QLinearGradient(0, 0, 0, 1)
            gradient.setCoordinateMode(QtGui.QGradient.ObjectBoundingMode)
            color = QtGui.QColor(options['background'])
            color.setAlpha(200)
            gradient.setColorAt(0, color)
            gradient.setColorAt(1, options['background'])
            painter.fillRect(0, h, w, hRefl, gradient)
            painter.end()
    
    def _clearCache(self):
        """Delete the cached version. Use this whenever options which affect
        the cached version have changed."""
        self._cache = None


# Make sure that this file can be used stand-alone for testing purposes
class CoverFlowWidget(coverbrowser.AbstractCoverWidget if __name__ != "__main__" else QtGui.QWidget):
    """
    Options:
    
    background: QColor to fill the background.
    size: QSize. The size of the central cover.
    coversPerSide: int. Number of covers visible to the left and right of the central cover.
    curve: string. The size of covers is computed by arranging them (virtually and when seen from above)
           on a curve. The central cover is "nearest" to the user and will use a scale factor of 1.
           The outermost covers are "farthest" to the user and will be scaled using MIN_SCALE.
           One of:
                "arc" arc segment,
                "v": v-shape/abs function,
                "cos": cos function,
                "cossqrt": cos curve differently parametrized,
                "peak": peak build of two parabel halves,
                "gallery": show all covers at MIN_SCALE except the central one.
    segmentRads: float in (0, pi]. Only for curve=="arc". Determines the length of the arc segment on which
                 covers are positioned. Use π to arrange covers on a semicircle.
    minScale: float in (0, 1]. Scale factor used for the outermost positions.
    vAlign: float in [0,1]. Vertical align of whole coverflow (or equivalently the central cover).
            0: top, 1: bottom, linear in between (0.5: centered).
    coverVAlign: float in [0,1]. Vertical align of covers among each other.
                 0: the top edge is aligned, 1: the bottom edge is aligned, linear in between.
    reflection: bool. Enable/disable reflection.
    reflectionFactor: float in [0,1]. Ratio of reflection height divided by cover height
    fadeOut: bool. Fade out covers on both sides.
    fadeStart: float in [0, 1]. If fadeOut is True, covers will start fading out on both sides at the 
               position specified by fadeStart, i.e. 0 means that all covers will fade out, 1 means that
               only covers at the outermost position will fade out.
    """
    indexChanged = QtCore.pyqtSignal(int)   
    
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.WheelFocus)
        
        self.covers = []
        self._pos = 0     
        if state is None:
            state = {}   
        self._o = {
            'background': QtGui.QColor(*state['background']) \
                        if 'background' in state else QtGui.QColor(0,0,0),
            'size': QtCore.QSize(state['size'][0], state['size'][1]) \
                        if 'size' in state else QtCore.QSize(300, 300),
            'coversPerSide': state.get('coversPerSide', 5),
            'curve': state.get('curve', 'arc'),
            'segmentRads': 0.8*math.pi,
            'minScale': 0.3,
            'vAlign': 0.5 if not state.get('reflection') else 0.7,
            'coverVAlign': 0.8,
            'reflection': state.get('reflection', True),
            'reflectionFactor': 0.6,
            'fadeOut': state.get('fadeOut', True),
            'fadeStart': 0.4
        }
        
        self.renderer = Renderer(self)
        self.animator = Animator(self)
        self.clear() # initialize
     
    @classmethod
    def getTitle(cls):
        return translate("CoverBrowser", "Coverflow")
    
    def option(self, key):
        """Return the value of the option with the given key."""
        return self._o[key]
      
    def options(self):
        """Return a dict with all options."""
        return self._o.copy()
    
    def setOption(self, key, value):
        """Set the option with the given key."""
        self.setOptions({key: value})
        
    def setOptions(self, options):
        """Set several options: *options* must be a dict mapping option keys to values. Options which are
        not contained in *options* remain unchanged."""
        types = {
            'background': QtGui.QColor,
            'size': QtCore.QSize,
            'coversPerSide': int,
            'curve': str,
            'segmentRads': float,
            'minScale': float,
            'vAlign': float,
            'coverVAlign': float,
            'reflection': bool,
            'reflectionFactor': float,
            'fadeOut': bool,
            'fadeStart': float
        }
        changed = []
        for key, value in options.items(): # update only existing keys
            if key in self._o:
                type = types[key]
                if not isinstance(value, type) and not (type == float and isinstance(value, int)):
                    raise TypeError("Option '{}' must be of type {}. Received: {}".format(key, type, value))
                if value != self._o[key]:    
                    self._o[key] = value
                    changed.append(key)
        if any(k in changed for k in ['background', 'size', 'reflection', 'reflectionFactor']):
            for cover in self.covers:
                cover._clearCache()
        if len(changed):
            self.triggerRender()
        
    def coverCount(self):
        """Return the number of covers."""
        return len(self.covers)
        
    def setCovers(self, ids, coverPaths):
        self.animator.stop()
        self.covers = [Cover(id, coverPaths[id]) for id in ids]
        self._pos = min(len(self.covers)//2, self._o['coversPerSide'])
        self.triggerRender()
        
    def clear(self):
        """Remove all covers from display."""
        self.setCovers([], None)
        
    def showPrevious(self):
        """Move to the previous cover (using animation)."""
        pos = math.floor(self._pos)
        if pos == self._pos:
            pos -= 1
        self.showPosition(pos)
    
    def showNext(self):
        """Move to the next cover (using animation)."""
        pos = math.ceil(self._pos)
        if pos == self._pos:
            pos += 1
        self.showPosition(pos)
    
    def showPosition(self, position):
        """Move to the cover at *position* (using animation). *position* must be an index of self.covers."""
        position = max(0, min(position, len(self.covers)-1))
        if position != self._pos:
            self.animator.start(position)
        else: self.animator.stop()
        
    def setPosition(self, position):
        """Move directly to the cover at *position*, i.e. without animation.
        *position* must be an index of self.covers."""
        position = max(0, min(position, len(self.covers)-1))
        self.animator.stop()
        if position != self._pos:
            self._pos = position
            self.triggerRender()
        
    def paintEvent(self, event):
        self.renderer.paint()
        
    def triggerRender(self):
        """Schedule a repaint of the cover flow."""
        self.renderer.dirty = True
        self.update()
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Left:
            self.showPosition(self.animator.target()-1)
            event.accept()
        elif event.key() == Qt.Key_Right:
            self.showPosition(self.animator.target()+1)
            event.accept()
        else:
            event.ignore()
            
    def wheelEvent(self, event):
        self.showPosition(self.animator.target() - round(event.delta()/120))
        event.accept()
    
    def coverAt(self, point):
        """Return the Cover-instance at the given point (or None)."""
        if isinstance(point, QtCore.QPoint):
            point = QtCore.QPointF(point)
        o = self._o
        centerIndex = max(0, min(round(self._pos), len(self.covers)-1))
        rect = self.renderer.coverRect(centerIndex)
        if rect.contains(point):
            return self.covers[centerIndex]
        
        coversLeft = coversRight = o['coversPerSide']
        if self._pos < round(self._pos):
            coversLeft += 1
        elif self._pos > round(self._pos):
            coversRight += 1
            
        if point.x() < rect.left():
            # test covers to the left
            for index in reversed(range(max(0, centerIndex-coversLeft), centerIndex)):
                rect = self.renderer.coverRect(index)
                if rect.contains(point):
                    return self.covers[index]
                elif point.x() >= rect.left():
                    return None
        elif point.x() > rect.right():
            # test covers to the right
            for index in range(centerIndex+1, min(centerIndex+coversRight+1, len(self.covers))):
                rect = self.renderer.coverRect(index)
                if rect.contains(point):
                    return self.covers[index]
                elif point.x() <= rect.right():
                    return None
        return None
    
    def wrapperAt(self, point):
        """Return the wrapper (with all contents loaded) at the given point (or None)."""
        cover = self.coverAt(point)
        if cover is not None:
            wrapper = nodes.Wrapper(levels.real.get(cover.elid))
            wrapper.loadContents(recursive=True)
            return wrapper
        else: return None
    
    def mousePressEvent(self, event):
        self._mousePressPosition = event.pos()
        wrapper = self.wrapperAt(event.pos())
        if wrapper is not None:
            selection.setGlobalSelection(selection.Selection(levels.real, [wrapper]))
        super().mousePressEvent(event)
            
    def mouseDoubleClickEvent(self, event):
        wrapper = self.wrapperAt(event.pos())
        if wrapper is not None:
            playlist.appendToDefaultPlaylist([wrapper], replace=event.modifiers() & Qt.ControlModifier)
        event.accept()
    
    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and (event.pos() - self._mousePressPosition).manhattanLength() \
                                                >= QtGui.QApplication.startDragDistance():
            wrapper = self.wrapperAt(event.pos())
            if wrapper is not None:
                drag = QtGui.QDrag(self)
                mimeData = selection.MimeData(selection.Selection(levels.real, [wrapper]))
                drag.setMimeData(mimeData)
                drag.setPixmap(wrapper.element.getCover(100))
                drag.setHotSpot(QtCore.QPoint(50, 50))
                drag.exec_()
                self.setCursor(Qt.OpenHandCursor)
            
    def resizeEvent(self, event):
        self.triggerRender()
        super().resizeEvent(event)
        
    def createConfigWidget(self, parent):
        return ConfigWidget(self, parent)
    
    def state(self):
        bg = self.option('background')
        size = self.option('size')
        return {
            'background': (bg.red(), bg.green(), bg.blue()),
            'size': (size.width(), size.height()),
            'coversPerSide': self.option('coversPerSide'),
            'curve': self.option('curve'),
            'reflection': self.option('reflection'),
            'fadeOut': self.option('fadeOut'),
        }
        
      
class Renderer:
    """Renderer for the cover flow. The renderer will render the covers of the given CoverFlowWidget into
    an internal buffer and draw that buffer to the widget."""
    def __init__(self, widget):
        self.widget = widget
        self._o = widget._o
        self.init()
    
    def init(self):
        """Initialize the internal buffer. Call this whenever the widget's size has changed."""
        self.size = self.widget.size()
        self.buffer = QtGui.QPixmap(self.size)
        self.dirty = True
    
    def paint(self):
        """Render covers if self.dirty is true. In any case copy the buffer to the CoverFlowWidget."""
        if self.widget.size() != self.size:
            self.init()
        
        if self.dirty:
            self.render()
        
        painter = QtGui.QPainter(self.widget)
        painter.drawPixmap(0, 0, self.buffer)
  
    def render(self):
        """Render background and all covers."""
        self.buffer.fill(self._o['background'])
        self.renderCovers()
        self.dirty = False
        
    def renderCovers(self):
        """Render all covers."""
        if len(self.widget.covers) == 0:
            return
        o = self._o
        painter = QtGui.QPainter(self.buffer)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        dx, dy = self._getTranslation()
        painter.translate(dx, dy)
        
        centerIndex = max(0, min(round(self.widget._pos), len(self.widget.covers)-1))
        centerRect = self.renderCover(painter, centerIndex)
        clipRect = QtCore.QRect(-dx, -dy, dx+centerRect.left(), self.buffer.height())
        coversLeft = coversRight = o['coversPerSide']
        if self.widget._pos < round(self.widget._pos):
            coversLeft += 1
        elif self.widget._pos > round(self.widget._pos):
            coversRight += 1
        for i in reversed(range(max(0, centerIndex-coversLeft), centerIndex)):
            painter.setClipRect(clipRect)
            rect = self.renderCover(painter, i)
            if rect is None:
                break
            clipRect.setRight(min(clipRect.right(), rect.left()-1))
        clipRect = QtCore.QRect(centerRect.right(),
                                -dy,
                                self.buffer.width()-centerRect.right(),
                                self.buffer.height())
        for i in range(centerIndex+1, min(centerIndex+coversRight+1, len(self.widget.covers))):
            painter.setClipRect(clipRect)
            rect = self.renderCover(painter, i)
            if rect is None:
                break
            clipRect.setLeft(max(clipRect.left(), rect.right()))
            
        painter.end()

    def _getTranslation(self):
        """Return the translation of the coordinate system used for drawing covers as (dx, dy)."""
        o = self._o
        dx = self.buffer.width() // 2
        if o['reflection']:
            necessaryHeight = (1+o['reflectionFactor']) * o['size'].height()
        else: necessaryHeight = o['size'].height()
        dy = int((self.buffer.height()-necessaryHeight) * o['vAlign'])
        return (dx, dy)
        
    def coverRect(self, index, translate=True):
        """Return the rectangle of a cover (identified by an index within the list of covers). The
        rectangle is the area in which the cover is rendered, including parts that are behind other covers.
        If *translate* is set to false the result will be relative to the coordinate system used for
        drawing. Otherwise it will be relative to the widgets usual coordinate system.
        """
        o = self._o
        w = o['size'].width()
        h = o['size'].height()
        
        # When seen from above, the covers are arranged on a curve, with the central cover
        # being "nearest" to the user and the outermost covers being "farthest".
        # This is then used to determine the scale factors in the front view.
        # The curve is between [-1,1] for x and [0,1] for z
        if o['curve'] == "arc":
            radians = (index-self.widget._pos) / o['coversPerSide'] * o['segmentRads'] / 2
            x = math.sin(radians)/abs(math.sin(o['segmentRads']/2))
            minCos = math.cos(o['segmentRads']/2)
            z = (math.cos(radians)-minCos)/(1.-minCos) # between 0 and 1
        elif o['curve'] == "v":
            x = (index-self.widget._pos) / o['coversPerSide']
            z = 1.-abs(x)
        elif o['curve'] == "cos":
            x = (index-self.widget._pos) / o['coversPerSide']
            z = math.cos(x*math.pi/2.) # between 0 and 1
        elif o['curve'] == "cossqrt":
            x = (index-self.widget._pos) / o['coversPerSide']
            if x >= 0:
                x = math.sqrt(x)
            else: x = -math.sqrt(-x)
            z = math.cos(x*math.pi/2.) # between 0 and 1
        elif o['curve'] == "peak":
            x = (index-self.widget._pos) / o['coversPerSide']
            if x >= 0:
                z = (x-1)**2
            else: z = (x+1)**2
        elif o['curve'] == "gallery":
            x = (index-self.widget._pos) / o['coversPerSide']
            if abs(x) >= 1./o['coversPerSide']:
                z = 0
            elif x >= 0:
                z = (x*o['coversPerSide'] - 1)**2
            else:
                z = (x*o['coversPerSide'] + 1)**2
        else:
            assert False
         
        # Scale x from [-1, 1] to pixel coordinates (x refers to the center of the cover)
        x *= self._availableWidth() / 2
            
        if z > 1:
            z = 1
        scale = o['minScale'] + z * (1.-o['minScale'])
        y = (1-scale) * h * o['coverVAlign']
        
        pixmap = self.widget.covers[index].cache(self._o)
        rect = QtCore.QRectF(round(x-scale*w/2), y, round(scale*pixmap.width()), scale*pixmap.height())
        if translate:
            rect.translate(*self._getTranslation())
        return rect
        
    def _availableWidth(self):
        """Return the width of the region that can be used for the center of covers. This is a bit less than
        the widget's width to leave enough space at the edges so that the outer images are completely
        visible."""
        return self.buffer.width() - self._o['minScale']*self._o['size'].width()
        
    def renderCover(self, painter, index):
        """Render the cover at *index* (index within the list of covers) using the given QPainter. Return
        the cover's rectangle."""
        o = self._o
        cover = self.widget.covers[index]
        pixmap = cover.cache(self._o)
        rect = self.coverRect(index, translate=False)
        painter.drawPixmap(rect, pixmap, QtCore.QRectF(pixmap.rect()))

        if o['fadeOut']:
            # Scale x into [-1, 1] (this inverts a scaling in self.coverRect)
            x = rect.center().x() / self._availableWidth() * 2
            if abs(x) > o['fadeStart']:
                alpha = round(255 * max(0, 1-(abs(x)-o['fadeStart'])))
                if alpha < 255:
                    color = QtGui.QColor(o['background'])
                    color.setAlpha(255-alpha)
                    painter.fillRect(rect, color)
            
        return rect


class Animator:
    """This class moves covers during animation."""
    INTERVAL = 30
    
    def __init__(self, widget):
        self.widget = widget
        self.timer = QtCore.QTimer()
        self.timer.setInterval(self.INTERVAL)
        self.timer.timeout.connect(self.update)
        self._target = None
        self._start = None
        self._a = 4. / self.INTERVAL  # acceleration
        self._v = 0.                  # velocity
        
    def target(self):
        """Return the current target index."""
        if self._target is not None:
            return self._target
        else: return self.widget._pos
       
    def start(self, target):
        """Start animation moving to the given target index."""
        target = max(0, min(target, len(self.widget.covers)-1))
        if not self.timer.isActive() \
                or (self._target - self.widget._pos) * (target - self.widget._pos) < 0: # different direction
            self._target = target
            self._v = 0.
            self.timer.start()
        else:
            self._target = target
       
    def stop(self):
        """Stop animation immediately."""
        self.timer.stop()
        self._target = None
        
    def update(self):
        """Called by the timer: Move animated covers to the next position."""
        t = self._target
        if self.widget._pos == t:
            self.stop()
            return
        dist = abs(t - self.widget._pos)
        self._v = min(self._v + self._a, math.sqrt(2*self._a*dist))
        if t > self.widget._pos:
            self.widget._pos = min(t, self.widget._pos + self._v)
        else: self.widget._pos = max(t, self.widget._pos - self._v)
        self.widget.triggerRender()
        
        
class ConfigWidget(QtGui.QWidget):
    """Configuration widget for AbstractCoverWidget.createConfigWidget. Allows to change some but not all
    options of CoverFlowWidget."""
    def __init__(self, coverFlow, parent):
        super().__init__(parent)
        self.coverFlow = coverFlow
        layout = QtGui.QFormLayout(self)
        
        sliderLayout = QtGui.QHBoxLayout()
        sizeSlider = QtGui.QSlider(Qt.Horizontal) 
        sizeSlider.setMinimum(100)
        sizeSlider.setMaximum(500)
        size = coverFlow.option('size').width()
        sizeSlider.setValue(size)
        sizeSlider.valueChanged.connect(lambda x: coverFlow.setOption('size', QtCore.QSize(x,x)))
        sliderLayout.addWidget(sizeSlider)
        sizeLabel = QtGui.QLabel(str(size))
        sizeSlider.valueChanged.connect(lambda x,l=sizeLabel: l.setText(str(x)))
        sliderLayout.addWidget(sizeLabel)
        layout.addRow(translate("CoverFlow", "Cover size"), sliderLayout)

        self.curveBox = QtGui.QComboBox()
        for title, key in CURVES:
            self.curveBox.addItem(title, key)
            if key == coverFlow.option('curve'):
                self.curveBox.setCurrentIndex(self.curveBox.count()-1)
        self.curveBox.currentIndexChanged.connect(self._handleCurveBox)
        layout.addRow(translate("CoverFlow", "Curve"), self.curveBox)
        
        self.colorBox = QtGui.QComboBox()
        for title, key in COLORS:
            self.colorBox.addItem(title, key)
            if key == coverFlow.option('background'):
                self.colorBox.setCurrentIndex(self.colorBox.count()-1)
        self.colorBox.currentIndexChanged.connect(self._handleColorBox)
        layout.addRow(translate("CoverFlow", "Background"), self.colorBox)
        
        sliderLayout = QtGui.QHBoxLayout()
        numberSlider = QtGui.QSlider(Qt.Horizontal) 
        numberSlider.setMinimum(1)
        numberSlider.setMaximum(7)
        numberSlider.setValue(coverFlow.option('coversPerSide'))
        numberSlider.valueChanged.connect(functools.partial(coverFlow.setOption, 'coversPerSide'))
        sliderLayout.addWidget(numberSlider)
        sizeLabel = QtGui.QLabel(str(coverFlow.option('coversPerSide')))
        numberSlider.valueChanged.connect(lambda x,l=sizeLabel: l.setText(str(x)))
        sliderLayout.addWidget(sizeLabel)
        layout.addRow(translate("CoverFlow", "Covers per side"), sliderLayout)
        
        reflectionBox = QtGui.QCheckBox()
        reflectionBox.setChecked(coverFlow.option('reflection'))
        reflectionBox.toggled.connect(self._handleReflectionBox)
        layout.addRow(translate("CoverFlow", "Reflection"), reflectionBox)
        
        fadeOutBox = QtGui.QCheckBox()
        fadeOutBox.setChecked(coverFlow.option('fadeOut'))
        fadeOutBox.toggled.connect(functools.partial(coverFlow.setOption, 'fadeOut'))
        layout.addRow(translate("CoverFlow", "Fade out"), fadeOutBox)
        
    def _handleCurveBox(self, index):
        self.coverFlow.setOption('curve', self.curveBox.itemData(index))
        
    def _handleColorBox(self, index):
        self.coverFlow.setOption('background', self.colorBox.itemData(index))
        
    def _handleReflectionBox(self, checked):
        self.coverFlow.setOption('reflection', checked)
        self.coverFlow.setOption('vAlign', 0.7 if checked else 0.5)


# Test code to test cover flow without main application.
if __name__ == "__main__":
    import os, os.path
    app = QtGui.QApplication([])
    coverFolder = os.path.expanduser('~/.config/omg/covers/large')
    coverPaths = {i: os.path.join(coverFolder, filename)
                  for i, filename in enumerate(os.listdir(coverFolder))}
    ids = list(coverPaths.keys())
    import random
    random.shuffle(ids)
    widget = QtGui.QWidget()
    widget.resize(1400, 600)
    layout = QtGui.QVBoxLayout(widget)
    layout.setContentsMargins(0,0,0,0)
    layout.setSpacing(0)
    configLayout = QtGui.QHBoxLayout()
    curveBox = QtGui.QComboBox()
    curveBox.addItems([c[1] for c in CURVES])
    def handleCurveBox(index):
        coverWidget.setOption('curve', curveBox.currentText())
    curveBox.currentIndexChanged.connect(handleCurveBox)
    configLayout.addWidget(curveBox)
    configLayout.addStretch()
    layout.addLayout(configLayout)
    coverWidget = CoverFlowWidget(None)
    coverWidget.setCovers(ids, coverPaths)
    layout.addWidget(coverWidget)
    widget.show()
    coverWidget.setFocus(Qt.ActiveWindowFocusReason)
    app.exec_()
