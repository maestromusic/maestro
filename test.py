import sys
from PyQt4 import QtCore, QtGui
from omg import tags, database
from omg.browser import forestmodel, delegate, layouter

database.connect()
tags.updateIndexedTags()

class Node:
    def __init__(self,title,elements = []):
        self.title = title
        self.elements = elements
    
    def getElements(self):
        return self.elements
        
    def getElementsCount(self):
        return len(self.elements)
    
    def getTitle(self):
        return self.title
        
    def __str__(self):
        return self.title
    
root = Node('1',[Node('2',[Node('3',[Node('4',[])])])])
        
model = forestmodel.ForestModel([root])

#~ index1 = model.index(0,0)
#~ index2 = model.index(0,0,index1)
#~ index3 = model.index(0,0,index2)
#~ index4 = model.index(0,0,index3)
#~ print(model.data(index4))

if __name__ == "__main__":
    app = QtGui.QApplication(sys.argv)
    browser = QtGui.QTreeView(None)
    browser.setHeaderHidden(True)
    browser.setModel(model)
    #browser.expandToDepth(2)
    browser.resize(299, 409)
    screen = QtGui.QDesktopWidget().screenGeometry()
    size =  browser.geometry()
    browser.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)

    browser.show()
    sys.exit(app.exec_())