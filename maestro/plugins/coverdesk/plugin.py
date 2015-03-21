# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2015 Martin Altmayer, Michael Helmling
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

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
translate = QtCore.QCoreApplication.translate

from maestro import config, utils, widgets, logging
from maestro.core import levels, covers, tags, elements, domains
from maestro.gui import selection
from maestro.plugins.coverdesk import actions


def enable():        
    widgets.addClass(
        id = "coverdesk",
        name = translate("CoverDesk", "Coverdesk"),
        icon = utils.images.icon('widgets/coverdesk.png'),
        theClass = CoverDesk,
        areas = 'central, dock',
        preferredDockArea = 'right'
    )
    
def disable():
    widgets.removeClass("coverdesk")
    
    
    
class CoverDesk(widgets.Widget):
    """A CoverDesk contains a GraphicsView with a DesktopScene which lets the user freely position objects
    (mainly element covers).
    """
    hasOptionDialog = True

    def __init__(self, state=None, **args):
        super().__init__(**args)
        layout = QtWidgets.QHBoxLayout(self)
        scene = DesktopScene(self)
        
        if state is not None:
            if 'items' in state:
                try:
                    levels.real.collect([t[0] for t in state['items'] if isinstance(t[0], int)])
                    items = []
                    for t in state['items']:
                        if t[0] == 'stack':
                            item = StackItem.fromState(scene, t)
                        else: item = CoverItem.fromState(scene, t)
                        scene.addItem(item)
                except Exception as e:
                    logging.warning(__name__, "Could not restore cover desk: "+str(e))
            if 'domain' in state:
                scene.domain = domains.domainById(state['domain'])
                
        self.view = QtWidgets.QGraphicsView(scene)
        self.view.setAcceptDrops(True)
        self.view.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.view.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        #self.view.scene().selectionChanged.connect(self.selectionChanged)
        layout.addWidget(self.view)
        self.view.ensureVisible(0, 0, 1, 1, 0, 0)
                    
    def saveState(self):
        items = [item.saveState() for item in self.view.scene().items()]
        return {'items': items, 'domain': self.view.scene().domain.id}

    def createOptionDialog(self, button=None):
        from maestro.gui import widgets as guiwidgets, dialogs
        dialog = dialogs.FancyPopup(button)
        layout = QtWidgets.QVBoxLayout(dialog)
        def setDomain(domain):
            self.view.scene().domain = domain
        domainBox = guiwidgets.DomainBox(self.view.scene().domain)
        domainBox.domainChanged.connect(setDomain)
        layout.addWidget(domainBox)
        layout.addStretch()
        dialog.show()
        
        
class DesktopScene(QtWidgets.QGraphicsScene):
    """A DesktopScene lets the user freely position objects (mainly element covers). It saves the positions
    and restores them at the next application launch. Objects may be moved using drag and drop.
    """
    maxSize = 100
    
    def __init__(self, parent):
        super().__init__(parent)
        self._frontItem = None
        self.setSceneRect(0, 0, 800, 600)
        self.domain = domains.domains[0]

    def contextMenuEvent(self, event):
        if self.itemAt(event.scenePos(), QtGui.QTransform()) is not None:
            super().contextMenuEvent(event)
        else:
            menu = QtWidgets.QMenu(event.widget())
            action = actions.AddStackAction(self, event.scenePos(), event.widget())
            menu.addAction(action)
            menu.exec_(event.screenPos())
            event.accept()

    def makePosition(self, position):
        """To position the center of an item at *position*, set its position to the one returned by this
        method."""
        x = max(0, min(position.x()-self.maxSize/2, self.width()-self.maxSize/2))
        y = max(0, min(position.y()-self.maxSize/2, self.height()-self.maxSize/2))
        return QtCore.QPointF(x, y)
        
    def addElements(self, elements, position):
        """Convenience method: Add CoverItems for the given elements at *position*."""
        for element in elements:
            item = CoverItem(self, element)
            item.setPos(self.makePosition(position))
            self.addItem(item)
        
    def selection(self):
        """Return a selection.Selection object based on the selected covers."""
        return None #TODO
        return selection.Selection.fromElements(levels.real,
                                    levels.real.collect([item.element.id for item in self.selectedItems()]))
        
    def helpEvent(self, helpEvent):
        # Note: Setting all tooltips when the scene is generated takes much too long. Reimplementing
        # QGraphicsItem.toolTip does not work for some reason. Thus we reimplement the code that displays
        # tooltips.
        item = self.itemAt(helpEvent.scenePos(), QtGui.QTransform())
        if item is not None:
            QtWidgets.QToolTip.showText(helpEvent.screenPos(), self._createToolTip(item))
        helpEvent.accept()
        
    def _createToolTip(self, item, coverSize=150, showTags=True, showFlags=False, showParents=True):
        """Create a tool tip for the given CoverItem."""
        #TODO: merge with RootedTreeModel.createWrapperToolTip
        return #TODO
        el = levels.real[item.element.id]
        lines = [el.getTitle()]
        if el.isFile() and el.url is not None:
            lines.append(str(el.url))
        elif el.isContainer():
            lines.append(el.type.title())
        if showTags and el.tags is not None:
            lines.extend("{}: {}".format(tag.title, ', '.join(map(str, values)))
                         for tag, values in el.tags.items() if tag != tags.TITLE)
        
        if showFlags and el.tags is not None and len(el.flags) > 0:
            lines.append(translate("RootedTreeModel", "Flags: ")+','.join(flag.name for flag in el.flags))
            
        if showParents and el.parents is not None:
            parentIds = list(el.parents)
            parents = levels.real.collect(parentIds)
            parents.sort(key=elements.Element.getTitle)
            lines.extend(translate("RootedTreeModel", "#{} in {}").format(p.contents.positionOf(el.id),
                                                                          p.getTitle())
                         for p in parents)
        
        # Escape tags for use in HTML
        import html
        lines = '<br/>'.join(html.escape(line) for line in lines)
        
        if coverSize is not None and el.hasCover():
            imgTag = el.getCoverHTML(coverSize, 'style="float: left"')
            return imgTag + '<div style="margin-left: {}">{}</div>'.format(coverSize+5, lines)
        else:
            # enclose in a div so that Qt formats this as rich text.
            # Otherwise HTML escapes would be printed as plain text.
            return '<div>{}</div>'.format(lines)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(config.options.gui.mime) \
                and Qt.CopyAction & event.possibleActions():
            event.setDropAction(Qt.CopyAction)
            event.acceptProposedAction()
            
    def dragMoveEvent(self, event):
        pass # delete super implementation which only accepts the event, if an item is under the cursor
        
    def dropEvent(self, event):
        mimeData = event.mimeData()
        if not Qt.CopyAction & event.possibleActions():
            return
        event.setDropAction(Qt.CopyAction)
        if mimeData.hasFormat(config.options.gui.mime):
            elements = [w.element for w in mimeData.toplevelWrappers()]
            level = mimeData.level
        else:
            logging.warning(__name__, "Invalid drop event (supports only {})"
                                      .format(", ".join(mimeData.formats())))
            return
        
        self.addElements(elements, event.scenePos())
        event.acceptProposedAction()
        

class DesktopItem(QtWidgets.QGraphicsItem):
    """Abstract base class for the items in a DesktopScene."""
    def __init__(self):
        super().__init__()
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsMovable)
    
    def contextMenuEvent(self, event):
        actions = self._getActions(event.widget())
        if len(actions) > 0:
            menu = QtWidgets.QMenu(event.widget())
            menu.addActions(actions)
            menu.exec_(event.screenPos())
        
    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        # Make sure the item does not leave the scene rect
        rect = self.boundingRect()
        if self.x() < 0:
            self.setX(0)
        elif self.x() > self.scene().width() - rect.width():
            self.setX(max(0, self.scene().width() - rect.width()))
            
        if self.y() < 0:
            self.setY(0)
        elif self.y() > self.scene().height() - rect.height():
            self.setY(max(0, self.scene().height() - rect.height()))
            
    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        items = self.collidingItems()
        if len(items):
            items[0].receiveItem(self)
        
    def receiveItem(self, item):
        """This is called when *item* is dropped onto this item."""
        pass
    
    def _getActions(self, parent):
        """Return a list of actions that should be used in the context menu for this item."""
        return [actions.DeleteItemAction(self, parent)]
           

class CoverItem(DesktopItem):
    """A CoverItem displays a single cover of an element. The cover is only loaded when it must be drawn
    for the first time. If *element* does not have a cover, a dummy cover is created.
    """
    def __init__(self, scene, element):
        super().__init__()
        self._scene = scene
        self.element = element
        self.pixmap = None
        self._scaled = None
        
    def saveState(self):
        return (self.element.id, self.x(), self.y())
    
    @staticmethod
    def fromState(scene, state):
        """Create a CoverItem from information stored by 'saveState'."""
        item = CoverItem(scene, levels.real[state[0]])
        item.setPos(state[1], state[2])
        return item
        
    def _load(self):
        """Load/create the cover for the element."""
        if self.element.hasCover():
            self.pixmap = self.element.getCover(self._scene.maxSize)
        else:
            title = self.element.getTitle()
            artist = ', '.join(self.element.tags['artist']) if 'artist' in self.element.tags else ''
            self.pixmap = makeCover(self._scene.maxSize, title, artist)
        self._scaled = utils.images.scale(self.pixmap, self._scene.maxSize)
            
    def scaled(self):
        """Return the scaled version of the cover."""
        if self._scaled is None:
            self._load()
        return self._scaled
            
    def mousePressEvent(self, event):
        if self._scene._frontItem is not None:
            self._scene._frontItem.setZValue(0)
        self.setZValue(1)
        self._scene._frontItem = self
        super().mousePressEvent(event) 
        
    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.scene():
            self.ungrabMouse()

    def boundingRect(self):
        size = self.scaled().size()
        return QtCore.QRectF(0, 0, size.width() + 2, size.height() + 2)
    
    def paint(self, painter, option, widget):
        painter.drawPixmap(1, 1, self.scaled())
        size = self.scaled().size()
        painter.drawRect(QtCore.QRectF(0, 0, size.width() + 1, size.height() + 1))
    
     
class StackItem(DesktopItem):
    """A stack contains a list of CoverItems. The user can scroll through the list using the mouse wheel.
    Items can be added and removed via drag and drop.
    
    A stack may have a title which is drawn below the stack. To move a stack around the user must grab it at
    its "handle". For stack with title this is the title area. For stack without title the handle is a small
    triangle in the bottom right corner.
    """
    TITLE_FONT_SIZE = 10
    HANDLE_SIZE = 10
    
    def __init__(self, title=''):
        super().__init__()
        self.items = []
        self.index = 0
        self.title = title
        self.size = QtCore.QSize(100, 100)
        self._handleLeft = 0
        #self.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlags())
        self.setAcceptHoverEvents(True)
        
    def saveState(self):
        return ('stack', self.x(), self.y(), self.title, [item.element.id for item in self.items])
    
    @staticmethod
    def fromState(scene, state):
        """Create a StackItem for the given scene from information stored by 'saveState'."""
        assert state[0] == 'stack'
        x, y, title, items = state[1:]
        item = StackItem(title)
        item.items = [CoverItem(scene, el) for el in levels.real.collect(items)]
        item.setPos(x, y)
        return item
         
    def addItem(self, item):
        """Add an item to the stack."""
        self.items.insert(self.index, item)
        self.update()
        
    def removeItem(self):
        """Remove the front item from the stack."""
        item = self.items.pop(self.index)
        self.index = max(0, self.index-1)
        self.update()
        return item
        
    def boundingRect(self):
        if self.title:
            font = self.scene().font()
            font.setPointSize(self.TITLE_FONT_SIZE)
            fm = QtGui.QFontMetrics(font)
            titleHeight = fm.height()
        else: titleHeight = 0
        return QtCore.QRectF(0, 0, self.size.width(), self.size.height() + titleHeight)
    
    def paint(self, painter, option, widget):
        itemRect = QtCore.QRectF(0, 0, self.size.width()-1, self.size.height()-1)
        if len(self.items) == 0:
            painter.drawRect(itemRect)
        else:
            pixmap = self.items[self.index].scaled()
            painter.drawPixmap(0, 0, pixmap)
            painter.drawRect(itemRect)
        
        # Draw title
        if self.title:
            font = painter.font()
            font.setPointSize(self.TITLE_FONT_SIZE)
            painter.setFont(font)
            fm = painter.fontMetrics()
            width = fm.width(self.title)
            height = fm.height()
            self._handleLeft = left = max(itemRect.left(), itemRect.right()+1 - width - 4)
            width = itemRect.right()+1 - left
            
            painter.fillRect(QtCore.QRectF(left, itemRect.bottom(), width, height+1), Qt.SolidPattern)
            pen = painter.pen()
            pen.setColor(QtGui.QColor(255, 255, 255))
            painter.setPen(pen)
            painter.drawText(QtCore.QRectF(left+2, itemRect.bottom(), width-4, height),
                             Qt.AlignLeft | Qt.TextSingleLine, self.title)
        else:
            if option.state & QtWidgets.QStyle.State_MouseOver:
                painter.setBrush(Qt.SolidPattern)
                painter.drawConvexPolygon(
                                  QtCore.QPointF(itemRect.right(), itemRect.bottom()),
                                  QtCore.QPointF(itemRect.right()-self.HANDLE_SIZE, itemRect.bottom()),
                                  QtCore.QPointF(itemRect.right(), itemRect.bottom()-self.HANDLE_SIZE))
            
    def receiveItem(self, item):
        if isinstance(item, CoverItem):
            self.scene().removeItem(item)
            self.addItem(item)

    def _isHandle(self, pos):
        """Return whether the given position belongs to the current handle for moving the stack."""
        if self.title:
            return pos.y() > self.size.height() and pos.x() >= self._handleLeft
        else:
            return pos.x() >= self.size.width() - self.HANDLE_SIZE \
                        and pos.y() >= self.size.height() - self.HANDLE_SIZE
        
    def hoverMoveEvent(self, event):
        if self._isHandle(event.pos()):
            self.setCursor(Qt.SizeAllCursor)
        else: self.setCursor(Qt.OpenHandCursor)
            
    def mousePressEvent(self, event):
        event.accept()
        if self._isHandle(event.pos()): # movement is handled by base class implementation
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._isHandle(event.buttonDownPos(Qt.LeftButton)):
            super().mouseMoveEvent(event)
            return
        if len(self.items) > 0:
            item = self.removeItem()
            item.setPos(self.pos())
            self.scene().addItem(item)
            self.ungrabMouse()
            item.grabMouse()
            
    def mouseReleaseEvent(self, event):
        if self._isHandle(event.buttonDownPos(Qt.LeftButton)):
            super().mouseReleaseEvent(event)
            
    def setIndex(self, index):
        """Set the current item to self.items[index]. *index* is allowed to be out of bounds."""
        index %= len(self.items)
        if index != self.index:
            self.index = index
            self.update()
    
    def wheelEvent(self, event):
        event.accept()
        if len(self.items) > 0:
            self.setIndex(self.index - event.delta() // 120)
        
    def _getActions(self, parent):
        actionList = super()._getActions(parent)
        actionList.insert(0, actions.ChangeStackTitleAction(self, parent))
        return actionList


def makeCover(size, title, artist):
    """Return a dummy cover for an element without cover. *size* specifies the size of the resulting QPixmap.
    *title* and *artist* are drawn as text into the pixmap.
    """
    PADDING = 3
    cover = QtGui.QPixmap(size, size)
    painter = QtGui.QPainter(cover)
    
    # Border and background
    #painter.setBrush(QtGui.QBrush(Qt.white))
    gradient = QtGui.QLinearGradient(QtCore.QPointF(0, 0), QtCore.QPointF(0, size))
    gradient.setColorAt(0, QtGui.QColor(0xeb,0xeb,0xeb))
    gradient.setColorAt(1, QtGui.QColor(0xcf,0xcf,0xcf))
    painter.fillRect(0, 0, size, size, gradient)
    
    # Title and artist
    font = painter.font()
    fontSize = font.pointSize()
    font.setPointSize(1.3*fontSize)
    painter.setFont(font)
    textRect = QtCore.QRectF(PADDING, PADDING, size-2*PADDING, 2*painter.fontMetrics().height())
    painter.drawText(textRect, Qt.AlignLeft | Qt.TextWordWrap, title)
    textRect.translate(0, textRect.height() + PADDING)
    font.setPointSize(fontSize)
    painter.setFont(font)
    textRect.setHeight(2*painter.fontMetrics().height())
    painter.drawText(textRect, Qt.AlignLeft | Qt.TextWordWrap, artist)
    return cover
        