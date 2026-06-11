"""State-machine node graph for the right panel.

Builds a draggable node graph from an experiment SPEC (states + transitions).
Because we're tuning existing coded experiments, this visualises the experiment's
state machine and highlights the live current state during a run; nodes can be
dragged to lay the graph out nicely.
"""

from PySide6 import QtCore, QtGui, QtWidgets

NODE_W = 170
NODE_H = 56


class StateNode(QtWidgets.QGraphicsObject):
    moved = QtCore.Signal()

    def __init__(self, state_id, label):
        super().__init__()
        self.state_id = state_id
        self.label = label
        self._active = False
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setZValue(1)

    def boundingRect(self):
        return QtCore.QRectF(0, 0, NODE_W, NODE_H)

    def center(self):
        return self.pos() + QtCore.QPointF(NODE_W / 2.0, NODE_H / 2.0)

    def set_active(self, active):
        if active != self._active:
            self._active = active
            self.update()

    def paint(self, painter, option, widget=None):
        rect = self.boundingRect().adjusted(1, 1, -1, -1)
        if self._active:
            painter.setBrush(QtGui.QColor(56, 142, 60))
            painter.setPen(QtGui.QPen(QtGui.QColor(165, 214, 167), 2))
        else:
            painter.setBrush(QtGui.QColor(55, 60, 70))
            painter.setPen(QtGui.QPen(QtGui.QColor(120, 130, 145), 1.5))
        painter.drawRoundedRect(rect, 10, 10)
        painter.setPen(QtGui.QColor(240, 240, 240))
        f = painter.font(); f.setPointSize(10); f.setBold(True); painter.setFont(f)
        painter.drawText(rect, QtCore.Qt.AlignCenter | QtCore.Qt.TextWordWrap, self.label)

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged:
            self.moved.emit()
        return super().itemChange(change, value)


class TransitionEdge(QtWidgets.QGraphicsPathItem):
    def __init__(self, src, dst, label):
        super().__init__()
        self.src = src
        self.dst = dst
        self.label = label
        self.setZValue(0)
        self.setPen(QtGui.QPen(QtGui.QColor(150, 160, 175), 1.8))
        self._text = QtWidgets.QGraphicsSimpleTextItem(label, self)
        self._text.setBrush(QtGui.QColor(170, 180, 195))
        self.adjust()

    def adjust(self):
        p1 = self.src.center()
        p2 = self.dst.center()
        path = QtGui.QPainterPath(p1)
        if self.src is self.dst:
            # self-loop
            r = QtCore.QRectF(p1.x() + NODE_W / 2 - 10, p1.y() - 50, 60, 50)
            path.addEllipse(r)
            self._text.setPos(r.center())
        else:
            path.lineTo(p2)
            mid = (p1 + p2) / 2.0
            self._text.setPos(mid.x() - self._text.boundingRect().width() / 2.0, mid.y() - 16)
        self.setPath(path)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self.src is self.dst:
            return
        # arrowhead pointing at dst's edge
        p1 = self.src.center()
        p2 = self.dst.center()
        line = QtCore.QLineF(p1, p2)
        if line.length() == 0:
            return
        # back off to the node border (~ half height)
        line.setLength(max(0.0, line.length() - NODE_H / 2.0))
        tip = line.p2()
        ang = line.angle()
        import math
        a = math.radians(ang)
        size = 10
        left = QtCore.QPointF(tip.x() - size * math.cos(a - math.radians(25)),
                              tip.y() + size * math.sin(a - math.radians(25)))
        right = QtCore.QPointF(tip.x() - size * math.cos(a + math.radians(25)),
                               tip.y() + size * math.sin(a + math.radians(25)))
        painter.setBrush(QtGui.QColor(150, 160, 175))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawPolygon(QtGui.QPolygonF([tip, left, right]))


class StateGraphView(QtWidgets.QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setBackgroundBrush(QtGui.QColor(38, 41, 48))
        self.setDragMode(QtWidgets.QGraphicsView.RubberBandDrag)
        self._nodes = {}
        self._edges = []

    def load_spec(self, spec):
        self._scene.clear()
        self._nodes = {}
        self._edges = []
        for st in spec.get("states", []):
            node = StateNode(st["id"], st.get("label", st["id"]))
            node.setPos(st.get("x", 0), st.get("y", 0))
            node.moved.connect(self._reposition_edges)
            self._scene.addItem(node)
            self._nodes[st["id"]] = node
        for tr in spec.get("transitions", []):
            src = self._nodes.get(tr["from"])
            dst = self._nodes.get(tr["to"])
            if src is None or dst is None:
                continue
            edge = TransitionEdge(src, dst, tr.get("label", ""))
            self._scene.addItem(edge)
            self._edges.append(edge)
        self._reposition_edges()
        if self._nodes:
            self.setSceneRect(self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40))

    def _reposition_edges(self):
        for e in self._edges:
            e.adjust()

    def set_current_state(self, state_id):
        for sid, node in self._nodes.items():
            node.set_active(sid == state_id)
