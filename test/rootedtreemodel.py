
import sys

from PyQt4 import QtCore,QtGui
from PyQt4.QtCore import Qt

from omg.models import rootedtreemodel
from omg.models import Node, RootNode


class TestNode(Node):
    def __init__(self,name,parent):
        self.name = name
        self.parent = parent
        self.contents = []

    def data(self,index,role=Qt.EditRole):
        if role == Qt.DisplayRole:
            return self.name
        else: return None

    def __str__(self):
        return self.name


root = RootNode()

def genChildren(node,level,number,prefix):
    children = []
    for i in range(number):
        name = prefix+str(i+1)
        child = TestNode(name,node)
        if level > 1:
            genChildren(child,level-1,number,name+".")
        children.append(child)
    node.contents = children


genChildren(root,4,3,"Node ")

def removeTest():
    model.remove(root.getChildren()[0].getChildren()[1])

def moveTest1():
    model.move(root.getChildren()[0].getChildren()[0],0,2,root.getChildren()[0],2)

def flattenTest():
    model.flatten(root.getChildren()[0])

def splitTest():
    model.split(root.getChildren()[0].getChildren()[0],1)

def insertParentTest():
    model.insertParent(root,0,1,TestNode("π",None))

testFunctions = [
    ("Entferne 1.2",removeTest),
    ("Bewege 1.2 und 1.3",moveTest1),
    ("Ebne 1.1 ein",flattenTest),
    ("Teile 1.1 bei 1",splitTest),
    ("Füge neuen Parent ein",insertParentTest)
]

app = QtGui.QApplication(sys.argv)
model = rootedtreemodel.RootedTreeModel(root)

widget = QtGui.QWidget()
widget.resize(500,400)
widget.setLayout(QtGui.QHBoxLayout())

treeview = QtGui.QTreeView(widget)
treeview.setModel(model)
treeview.expandAll()
widget.layout().addWidget(treeview)

buttonLayout = QtGui.QVBoxLayout()
widget.layout().addLayout(buttonLayout)
for name,function in testFunctions:
    button = QtGui.QPushButton(name,widget)
    button.clicked.connect(function)
    buttonLayout.addWidget(button)
buttonLayout.addStretch(1)

widget.show()
app.exec_()
