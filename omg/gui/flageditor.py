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

from . import dialogs
from .. import utils,config
from ..core import flags
from ..models import flageditor as flageditormodel,simplelistmodel


class FlagEditor(QtGui.QWidget):
    """A FlagEditor contains a label, a button to add new flags and a FlagListWidget that displays the
    model's records using FlagWidgets. It is used as part of the tageditor."""
    def __init__(self,model,vertical,parent=None):
        super().__init__(parent)
        self.setSizePolicy(QtGui.QSizePolicy.Expanding,QtGui.QSizePolicy.Fixed)
        
        self.setLayout(QtGui.QHBoxLayout())
        self.layout().setSpacing(0)
        self.layout().setContentsMargins(0,0,0,0)
        
        label = QtGui.QLabel() # Text will be set in setVertical
        label.setToolTip(self.tr("Flags"))
        label.setText('<img src=":omg/icons/flag_blue.png"> '+self.tr("Flags: "))
        self.layout().addWidget(label)
        
        self.addButton = QtGui.QPushButton()
        self.addButton.setIcon(utils.getIcon("add.png"))
        self.addButton.clicked.connect(self._handleAddButton)
        self.layout().addWidget(self.addButton)
        
        self.flagScrollArea = QtGui.QScrollArea()
        self.flagScrollArea.setWidgetResizable(True)
        self.flagScrollArea.setMaximumHeight(30)
        self.flagScrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.flagScrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.flagScrollArea.setViewportMargins(0,0,0,0)
        self.flagList = FlagListWidget(model,vertical)
        self.flagScrollArea.setWidget(self.flagList)
        self.flagList.installEventFilter(self)
        self.layout().addWidget(self.flagScrollArea,1)
    
    def eventFilter(self,object,event):
        if event.type() == QtCore.QEvent.MouseMove:
            # This makes the scrollarea scroll horizontally when the mouse approaches the border
            self.flagScrollArea.ensureVisible(event.pos().x(),event.pos().y(),25,0)
        return False
            
    def setVertical(self,vertical):
        """Set whether the list of FlagWidgets should be vertical or horizontical."""
        self.flagList.setVertical(vertical)
                 
    def _handleAddButton(self):
        """Ask the user to add a flag."""
        popup = AddFlagPopup(self.flagList.model,self.addButton)
        popup.show()


class FlagListWidget(QtGui.QWidget):
    """Displays a list of FlagWidgets representing the records in the FlagEditorModel *model*. *vertical*
    specifies the direction of the list. When a record is removed, the other records slide to fill the gap.
    """
    # The animation currently running (if any). This is used to stop the animation if the model changes.
    _animation = None
    
    def __init__(self,model,vertical):
        super().__init__()
        self.setMouseTracking(True)
        self.vertical = vertical
        
        self._flagWidgets = []
        self.model = model
        self.model.resetted.connect(self._handleReset)
        self.model.recordInserted.connect(self._handleRecordInserted)
        self.model.recordRemoved.connect(self._handleRecordRemoved)
        self.model.recordChanged.connect(self._handleRecordChanged)
        
        self.setLayout(QtGui.QBoxLayout(QtGui.QBoxLayout.TopToBottom if vertical
                                        else QtGui.QBoxLayout.LeftToRight))
        self.layout().setAlignment(Qt.AlignLeft)
        style = QtGui.QApplication.style()
        # Use horizontal spacing instead of left margin so that the distance to the add button equals
        # the distance between two FlagWidgets.
        self.layout().setContentsMargins(style.pixelMetric(style.PM_LayoutHorizontalSpacing),0,
                                         style.pixelMetric(style.PM_LayoutRightMargin),0)
        
        self._handleReset()
        
    def setVertical(self,vertical):
        """Set whether this editor display the flags vertically."""
        if vertical != self.vertical:
            self._stopAnimation()
            self.vertical = vertical
            self.layout().setDirection(
                            QtGui.QBoxLayout.TopToBottom if vertical else QtGui.QBoxLayout.LeftToRight)

    def _handleReset(self):
        """Reset the FlagEditor."""
        self._stopAnimation()
        for flagWidget in self._flagWidgets:
            self.layout().removeWidget(flagWidget)
            flagWidget.deleteLater()

        self._flagWidgets = []

        for record in self.model.records:
            flagWidget = FlagWidget(self.model,record)
            self.layout().insertWidget(len(self._flagWidgets),flagWidget)
            self._flagWidgets.append(flagWidget)

    def _handleRecordInserted(self,pos,record):
        """Insert a FlagWidget for the new record."""
        self._stopAnimation()
        flagWidget = FlagWidget(self.model,record)
        self.layout().insertWidget(self._mapToLayout(pos),flagWidget)
        self._flagWidgets.insert(pos,flagWidget)

    def _handleRecordRemoved(self,record):
        """Remove the FlagWidget for *record*. If flageditor_animation and there are FlagWidgets on the
        right of the removed one, start an animation to slide them to the left."""
        self._stopAnimation()
        for pos,flagWidget in enumerate(self._flagWidgets):
            if flagWidget.getRecord() == record:
                self.layout().removeWidget(flagWidget)
                self._flagWidgets.remove(flagWidget)

                # No need to start animation for the last flag
                if config.options.gui.flageditor.animation and pos < len(self._flagWidgets)\
                    and self.isVisible():
                    size = flagWidget.sizeHint()
                    empty = QtGui.QWidget()
                    if self.vertical:
                        empty.setMinimumHeight(size.height())
                        property = "minimumHeight"
                    else:
                        empty.setMinimumWidth(size.width())
                        property = "minimumWidth"
                    self.layout().insertWidget(self._mapToLayout(pos),empty)
                    self._animation = QtCore.QPropertyAnimation(empty,property,self)
                    self._animation.setDuration(250)
                    self._animation.setEndValue(0)
                    self._animation.setEasingCurve(QtCore.QEasingCurve.InOutSine)
                    self._animation.start(QtCore.QAbstractAnimation.DeleteWhenStopped)
                    self._animation.finished.connect(self._handleAnimationFinished)

                flagWidget.deleteLater()
                return

    def _handleRecordChanged(self,oldRecord,newRecord):
        """Update the FlagWidget whose record has changed."""
        self._stopAnimation()
        for flagWidget in self._flagWidgets:
            if flagWidget.getRecord() == oldRecord:
                flagWidget.setRecord(newRecord)
                return

    def _stopAnimation(self):
        """If there is an active animation, stop it."""
        if self._animation is not None:
            self._animation.stop()
            self._handleAnimationFinished()

    def _handleAnimationFinished(self):
        """When the animation is finished remove the empty widget used for the animation."""
        if self._animation is not None:
            empty = self._animation.targetObject()
            self.layout().removeWidget(empty)
            empty.deleteLater()
            self._animation = None

    def _mapToLayout(self,pos):
        """Map a position in self.flagWidgets to a position in the flageditor's boxlayout: Due to the
        animation the layout may contain an empty widget so that positions after this widget are shifted by
        one."""
        for i in range(self.layout().count()):
            widget = self.layout().itemAt(i).widget()
            if widget is not None and isinstance(widget,FlagWidget):
                if pos == 0:
                    return i
                else: pos -= 1
        else: return self.layout().count()
        
        
class FlagWidget(QtGui.QWidget):
    """Small widget representing a Record. It will display the flag's name and icon and if the record is not
    common also the number of elements that have the flag. Furthermore it contains a button to remove the
    record and provides some actions in a contextmenu.
    
        - model: the model containing the record
        - record: the record displayed by this FlagWidget
        - parent: the parent component
        
    \ """
    # Used to render the removeButton
    clearPixmap = utils.getIcon('clear_16.png').pixmap(16,16)

    # Whether the removeButton is visible
    _showRemoveButton = False

    # Whether the removeButton reacts to mouseReleasedEvents. To avoid clicking on the remove button
    # accidentally, it is enabled a split second after it has been shown.
    _removeButtonEnabled = False

    def __init__(self,model,record,parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setSizePolicy(QtGui.QSizePolicy.Fixed,QtGui.QSizePolicy.Fixed)
        self.model = model
        self.record = record
        self.setRecord(record)

    def getText(self):
        """Return the text displayed by this widget."""
        if self.record.isCommon():
            return self.record.flag.name
        else: return self.tr("{} (in {})").format(self.record.flag.name,len(self.record.elementsWithFlag))

    def getRecord(self):
        """Return the record displayed by this widget."""
        return self.record

    def setRecord(self,record):
        """Set the record displayed by this widget."""
        # Due to the string "(in 7)" the size of the widget depends on the number of records with flag.
        if (record.flag.name != self.record.flag.name
                or len(record.elementsWithFlag) != len(self.record.elementsWithFlag)):
            self.updateGeometry()
        self.record = record
        self.createToolTip()
        self.update()

    def createToolTip(self):
        """Build and set the tooltip of this FlagWidget."""
        # If the record is not common to all elements, display a tooltip containing the titles of those
        # elements that have the flag. But do not use more than flageditor_maxtooltiplines lines.
        if not self.record.isCommon():
            maxLines = config.options.gui.flageditor.max_tooltip_lines
            if len(self.record.elementsWithFlag) > maxLines:
                lines = [element.getTitle() for element in self.record.elementsWithFlag[:maxLines - 1]]
                lines.append(self.tr("(And %n other)",'',len(self.record.elementsWithFlag) - (maxLines - 1)))
            else: lines = [element.getTitle() for element in self.record.elementsWithFlag]
            self.setToolTip("\n".join(lines))

    def _sizes(self):
        """Return a tuple of sizes. These are e.g. necessary to draw the widget or to react correctly to
        mouse events."""
        fm = self.fontMetrics()
        borderWidth = 1
        textWidth = fm.width(self.getText())
        iconSize = 16
        smallHSpace = 4
        bigHSpace = 7
        vSpace = 1 # looks bigger because most characters are smaller than fm.height
        width = textWidth + 2 * (borderWidth + smallHSpace + iconSize + bigHSpace)
        height = fm.height() + 2 * vSpace + 2 * borderWidth
        return fm,borderWidth,textWidth,iconSize,smallHSpace,bigHSpace,vSpace,width,height

    def paintEvent(self,event):
        fm,borderWidth,textWidth,iconSize,smallHSpace,bigHSpace,vSpace,width,height = self._sizes()
        painter = QtGui.QPainter(self)
        painter.setPen(Qt.black)
        gradient = QtGui.QLinearGradient(0,0,0,1)
        gradient.setCoordinateMode(QtGui.QGradient.ObjectBoundingMode)
        gradient.setColorAt(0,QtGui.QColor(0x25,0xac,0xe4))
        gradient.setColorAt(1,QtGui.QColor(0x12,0x94,0xcb))
        painter.setBrush(gradient)
        painter.drawRect(0,0,width - 1,height - 1) # Take the pen width into account

        painter.setPen(Qt.white)
        painter.drawText(borderWidth + smallHSpace + iconSize + bigHSpace,
                         borderWidth + vSpace + fm.ascent(),
                         self.getText())


        if self.record.flag.icon is not None:
            pixmap = self.record.flag.icon.pixmap(16,16)
            painter.drawPixmap(borderWidth + smallHSpace,(height - iconSize) // 2,pixmap)

        if self._showRemoveButton:
            painter.drawPixmap(width - borderWidth - smallHSpace - iconSize,(height - iconSize) // 2,self.clearPixmap)

    def sizeHint(self):
        fm,borderWidth,textWidth,iconSize,smallHSpace,bigHSpace,vSpace,width,height = self._sizes()
        return QtCore.QSize(width,height)

    def mouseReleaseEvent(self,event):
        if self._removeButtonEnabled and event.button() == Qt.LeftButton:
            fm,borderWidth,textWidth,iconSize,smallHSpace,bigHSpace,vSpace,width,height = self._sizes()
            rect = QtCore.QRect(width - borderWidth - smallHSpace - iconSize,(height - iconSize) // 2,iconSize,iconSize)
            if rect.contains(event.pos()):
                self.model.removeFlag(self.record.flag)
            event.accept()
        else: event.ignore() # send to parent

    def enterEvent(self,event):
        self._showRemoveButton = True
        QtCore.QTimer.singleShot(250,self._handleTimer)
        self.update()

    def _handleTimer(self):
        """To avoid clicking on the remove button (which is invisible by default) accidentally, enable it a
        split second after it has been shown."""
        # Do not enable the button if the user left the component while the timer was running.
        if self._showRemoveButton:
            self._removeButtonEnabled = True

    def leaveEvent(self,event):
        self._showRemoveButton = False
        self._removeButtonEnabled = False
        self._pressed = False
        self.update()

    def contextMenuEvent(self,contextMenuEvent,record=None):
        menu = QtGui.QMenu(self)

        menu.addAction(self.model.stack.createUndoAction())
        menu.addAction(self.model.stack.createRedoAction())
        menu.addSeparator()

        if not self.record.isCommon():
            extendAction = QtGui.QAction(self.tr("Extend"),self)
            extendAction.triggered.connect(self._handleExtend)
            menu.addAction(extendAction)

        if len(self.record.allElements) > 1:
            elementsAction = QtGui.QAction(self.tr("Edit elements with flag..."),self)
            elementsAction.triggered.connect(self._handleEditElements)
            menu.addAction(elementsAction)

        menu.popup(contextMenuEvent.globalPos())

    def _handleExtend(self):
        """Extend the flag to all elements."""
        newRecord = flageditormodel.Record(self.record.flag,self.record.allElements,self.record.allElements)
        self.model.changeRecord(self.record,newRecord)

    def _handleEditElements(self):
        """Open a dialog that allows to edit self.record.elementsWithFlag."""
        dialog = EditElementsDialog(self.record,self)
        if dialog.exec_() == QtGui.QDialog.Accepted:
            selectedElements = dialog.getSelectedElements()
            if selectedElements != self.record.elementsWithFlag:
                newRecord = flageditormodel.Record(self.record.flag,self.record.allElements,
                                                   selectedElements)
                self.model.changeRecord(self.record,newRecord)


class AddFlagPopup(dialogs.FancyPopup):
    """Fancy popup that displays a list of flags that do not appear in one of the edited elements. If the 
    user clicks a flag, it will be added to all edited elements. Moreover the popup provides two buttons
    to create a new flag and to open the flagmanager."""
    def __init__(self,model,parent):
        super().__init__(parent)
        self.model = model
        self.setLayout(QtGui.QVBoxLayout())
        self.flagList = QtGui.QListWidget()
        self.flagList.itemClicked.connect(self._handleItemClicked)
        self.layout().addWidget(self.flagList)

        _flagTypes = sorted(flags.allFlags(),key=lambda f: f.name)
        for flag in _flagTypes:
            # Do not show flags which are already contained in all elements
            if self.model.getRecord(flag) is None or not self.model.getRecord(flag).isCommon():
                item = QtGui.QListWidgetItem(flag.name)
                item.setData(Qt.UserRole,flag)
                if flag.icon is not None:
                    item.setIcon(flag.icon)
                self.flagList.addItem(item)

        buttonLayout = QtGui.QHBoxLayout()
        self.layout().addLayout(buttonLayout)
        addFlagButton = QtGui.QPushButton(self.tr("New"))
        addFlagButton.clicked.connect(self._handleAddButton)
        buttonLayout.addWidget(addFlagButton)
        managerButton = QtGui.QPushButton(self.tr("FlagManager"))
        managerButton.clicked.connect(self._handleManagerButton)
        buttonLayout.addWidget(managerButton)

    def _handleAddButton(self):
        """Create a new flagtype (querying the user for the flagtype's name) and directly add it to all
        elements that are currently edited."""
        from .preferences import flagmanager
        flag = flagmanager.createNewFlagType(self.parent())
        if flag is not None:
            self.model.addFlag(flag)
        self.close()

    def _handleManagerButton(self):
        """Open the flagmanager."""
        from . import preferences
        preferences.show('main/flagmanager')
        self.close()

    def _handleItemClicked(self,item):
        """Add the clicked flag to all elements that are currently edited."""
        self.model.addFlag(item.data(Qt.UserRole))
        self.close()


class EditElementsDialog(QtGui.QDialog):
    """Small dialog that allows the user to choose which elements should have a specific flag. The flag and
    the elements that can be selected are contained in *record*."""
    def __init__(self,record,parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Edit elements with flag"))
        self.record = record

        self.setLayout(QtGui.QVBoxLayout())

        self.elementsBox = QtGui.QListView(self)
        self.layout().addWidget(self.elementsBox,1)
        self.elementsBox.setModel(simplelistmodel.SimpleListModel(self.record.allElements,
                                                                  lambda el: el.getTitle()))
        self.elementsBox.setSelectionMode(QtGui.QAbstractItemView.MultiSelection)
        for i,element in enumerate(self.record.allElements):
            if record is None or element in record.elementsWithFlag:
                self.elementsBox.selectionModel().select(self.elementsBox.model().index(i,0),
                                                         QtGui.QItemSelectionModel.Select)

        buttonLayout = QtGui.QHBoxLayout()
        buttonLayout.addStretch(1)
        self.layout().addLayout(buttonLayout)
        okButton = QtGui.QPushButton(self.tr("OK"))
        okButton.clicked.connect(self._handleOkButton)
        buttonLayout.addWidget(okButton)
        abortButton = QtGui.QPushButton(self.tr("Cancel"))
        abortButton.clicked.connect(self.reject)
        buttonLayout.addWidget(abortButton)

    def _handleOkButton(self):
        """Check whether at least one element is selected and if so, exit."""
        if self.elementsBox.selectionModel().hasSelection():
            self.accept()
        else: QtGui.QMessageBox.warning(self,self.tr("No element selected"),
                                        self.tr("You must select at lest one element."))

    def getSelectedElements(self):
        """Return the list of selected elements."""
        return [self.record.allElements[i] for i in range(len(self.record.allElements))
                                if self.elementsBox.selectionModel().isRowSelected(i,QtCore.QModelIndex())]
