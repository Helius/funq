# -*- coding: utf-8 -*-

# Copyright: SCLE SFE
# Contributor: Julien Pagès <j.parkouss@gmail.com>
# 
# This software is a computer program whose purpose is to test graphical
# applications written with the QT framework (http://qt.digia.com/).
# 
# This software is governed by the CeCILL v2.1 license under French law and
# abiding by the rules of distribution of free software.  You can  use, 
# modify and/ or redistribute the software under the terms of the CeCILL
# license as circulated by CEA, CNRS and INRIA at the following URL
# "http://www.cecill.info". 
# 
# As a counterpart to the access to the source code and  rights to copy,
# modify and redistribute granted by the license, users are provided only
# with a limited warranty  and the software's author,  the holder of the
# economic rights,  and the successive licensors  have only  limited
# liability. 
# 
# In this respect, the user's attention is drawn to the risks associated
# with loading,  using,  modifying and/or developing or reproducing the
# software by the user in light of its specific status of free software,
# that may mean  that it is complicated to manipulate,  and  that  also
# therefore means  that it is reserved for developers  and  experienced
# professionals having in-depth computer knowledge. Users are therefore
# encouraged to load and test the software's suitability as regards their
# requirements in conditions enabling the security of their systems and/or 
# data to be ensured and,  more generally, to use and operate it in the 
# same conditions as regards security. 
# 
# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL v2.1 license and that you accept its terms.

try:
    from PyQt4 import QtGui, QtCore
except ImportError:
    from PySide import QtGui, QtCore

import sys

def exec_dlg(self, dlgclass):
    def wrapper():
        dlg = dlgclass(self)
        dlg.exec_()
        # really destroy the dialog
        dlg.deleteLater()
    return wrapper

class MainWindow(QtGui.QMainWindow):
    def __init__(self, dialogs):
        QtGui.QMainWindow.__init__(self)
        self.setObjectName("mainWindow")
        self.setCentralWidget(QtGui.QWidget())
        layout = QtGui.QVBoxLayout()
        statusbar = QtGui.QStatusBar()
        statusbar.setObjectName("statusBar")
        self.statuslabel = QtGui.QLabel()
        statusbar.insertPermanentWidget(0, self.statuslabel)
        self.setStatusBar(statusbar)
        self.centralWidget().setLayout(layout)
        for name, dlgclass in dialogs.items():
            btn = QtGui.QPushButton(name)
            btn.setObjectName(name)
            btn.clicked.connect(exec_dlg(self, dlgclass))
            layout.addWidget(btn)

class SimpleDialog(QtGui.QDialog):
    def __init__(self, parent):
        QtGui.QDialog.__init__(self, parent)
        self.setLayout(QtGui.QVBoxLayout())
        for w in self._create_widgets():
            self.layout().addWidget(w)
    
    def showResult(self, msg):
        self.parent().statuslabel.setText(msg)
    
    def _create_widgets(self):
        raise NotImplementedError

class ClickDialog(SimpleDialog):
    def _create_widgets(self):
        btn = QtGui.QPushButton("click me")
        btn.clicked.connect(lambda: self.showResult("clicked !"))
        yield btn

class KeyClickDialog(SimpleDialog):
    def _create_widgets(self):
        line = QtGui.QLineEdit()
        line.textEdited.connect(lambda txt: self.showResult(txt))
        yield line

class DoubleClickDialog(SimpleDialog):
    def _create_widgets(self):
        w = QtGui.QWidget()
        w.resize(100, 100)
        yield w
    
    def mouseDoubleClickEvent (self, e):
        self.showResult("double clicked !")

class RetrieveWidget(SimpleDialog):
    def _create_widgets(self):
        yield QtGui.QLabel("hello")
        yield QtGui.QComboBox()

class ShortcutDialog(SimpleDialog):
    sequences = ["F2", "DOWN", "ENTER", "CTRL+C"]
    
    def on_shortcut(self, sequence):
        def slot():
            self.showResult("Shortcut: " + sequence)
        return slot
    
    def _create_widgets(self):
        shortcuts = []
        for sequence in self.sequences:
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(sequence), self)
            shortcut.activated.connect(self.on_shortcut(sequence))
            shortcuts.append(shortcut)
        self.shortcuts = shortcuts
        return []

class TableDialog(SimpleDialog):
    def on_hheader_clicked(self, index):
        self.showResult("H Header clicked: " + str(index))
    
    def on_vheader_clicked(self, index):
        self.showResult("V Header clicked: " + str(index))
    
    def _create_widgets(self):
        view = QtGui.QTableWidget(2, 3)
        view.setHorizontalHeaderLabels(['C1', 'C2', 'C3'])
        view.setVerticalHeaderLabels(['R1', 'R2'])
        for i in range(2):
            for j in range(3):
                view.setItem(i, j, QtGui.QTableWidgetItem(''))
        view.horizontalHeader().setObjectName('H')
        view.horizontalHeader().sectionClicked.connect(self.on_hheader_clicked)
        view.verticalHeader().setObjectName('V')
        view.verticalHeader().sectionClicked.connect(self.on_vheader_clicked)
        yield view


class MyItem(QtGui.QGraphicsRectItem):
    def __init__(self, *args):
        QtGui.QGraphicsRectItem.__init__(self, *args)

class MyQItem(QtGui.QGraphicsTextItem):
    def __init__(self, text, objname, pos):
        QtGui.QGraphicsTextItem.__init__(self, text)
        self.setAcceptDrops(True)
        self.setObjectName(objname)
        self.setPos(*pos)

    def mousePressEvent(self, event):
        self.setObjectName(str(self.objectName()) + "-clicked")
        # do not call the parent here to get more released event
        # see http://doc.qt.io/qt-4.8/qgraphicsitem.html#mousePressEvent

    def mouseReleaseEvent(self, event):
        self.setObjectName(str(self.objectName()) + "-released")

class GView(QtGui.QGraphicsView):
    def __init__(self, dlg):
        QtGui.QGraphicsView.__init__(self)
        self.dlg = dlg

    def mouseReleaseEvent(self, e):
        self.dlg.showResult("released!")
        return QtGui.QGraphicsView.mouseReleaseEvent(self, e)

class GraphicsViewDialog(SimpleDialog):
    def _create_widgets(self):
        view = GView(self)
        scene = QtGui.QGraphicsScene()

        view.setScene(scene)
        item = MyItem(0, 0, 100, 100)
        item.setBrush(QtGui.QBrush(QtGui.QColor(255, 0, 0, 127)))
        scene.addItem(item)
        scene.addItem(MyQItem("hello !", "textItem", (105, 0)))
        scene.addItem(MyQItem("hello2 !", "textItem2", (0, 105)))
        yield view

def main():
    dialogs = {
        "click": ClickDialog,
        'doubleclick': DoubleClickDialog,
        'keyclick': KeyClickDialog,
        'retrieve': RetrieveWidget,
        'shortcut': ShortcutDialog,
        'table': TableDialog,
        "gview": GraphicsViewDialog,
    }
    
    app = QtGui.QApplication(sys.argv)
    win = MainWindow(dialogs)
    win.resize(800, 600)
    win.show()
    app.exec_()

if __name__ == '__main__':
    main()
