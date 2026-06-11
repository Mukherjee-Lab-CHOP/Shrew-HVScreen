"""State-machine node graph for the right panel.

Builds a draggable node graph from an experiment SPEC (states + transitions).
Because we're tuning existing coded experiments, this visualises the experiment's
state machine and highlights the live current state during a run; nodes can be
dragged to lay the graph out nicely.
"""

import math

from PySide6 import QtCore, QtGui, QtWidgets

NODE_W = 170
NODE_H = 56
EDGE_COLOR = QtGui.QColor(190, 200, 215)


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
    """A transition arrow. Endpoints are clipped to the node borders (so the
    line never hides under a node), reciprocal edges curve to opposite sides so
    they don't overlap, the arrowhead sits on the destination border, and the
    label has an opaque background. Drawn ABOVE the nodes so it's never hidden."""

    def __init__(self, src, dst, label):
        super().__init__()
        self.src = src
        self.dst = dst
        self.setZValue(2)                       # above nodes (z=1)
        self.setPen(QtGui.QPen(EDGE_COLOR, 2.2))
        self._tip = QtCore.QPointF()
        self._from = QtCore.QPointF()
        self._label_bg = QtWidgets.QGraphicsRectItem(self)
        self._label_bg.setBrush(QtGui.QColor(34, 37, 44))
        self._label_bg.setPen(QtGui.QPen(QtGui.QColor(90, 100, 115)))
        self._text = QtWidgets.QGraphicsSimpleTextItem(label, self)
        self._text.setBrush(QtGui.QColor(215, 222, 232))
        self.adjust()

    def _border_point(self, node, toward):
        c = node.center()
        dx, dy = toward.x() - c.x(), toward.y() - c.y()
        if dx == 0 and dy == 0:
            return c
        sx = (NODE_W / 2.0) / abs(dx) if dx else float("inf")
        sy = (NODE_H / 2.0) / abs(dy) if dy else float("inf")
        s = min(sx, sy)
        return QtCore.QPointF(c.x() + dx * s, c.y() + dy * s)

    def adjust(self):
        if self.src is self.dst:
            c = self.src.center()
            r = QtCore.QRectF(c.x() - 28, c.y() - NODE_H / 2.0 - 46, 56, 46)
            path = QtGui.QPainterPath()
            path.addEllipse(r)
            self.setPath(path)
            self._tip = QtCore.QPointF(r.center().x() + 10, r.bottom())
            self._from = QtCore.QPointF(r.center().x() - 10, r.bottom())
            self._place_label(QtCore.QPointF(r.center().x(), r.top() - 2))
            return
        cs, cd = self.src.center(), self.dst.center()
        p1 = self._border_point(self.src, cd)
        p2 = self._border_point(self.dst, cs)
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length          # perpendicular unit
        offset = 26.0
        mid = QtCore.QPointF((p1.x() + p2.x()) / 2.0, (p1.y() + p2.y()) / 2.0)
        ctrl = QtCore.QPointF(mid.x() + nx * offset, mid.y() + ny * offset)
        path = QtGui.QPainterPath(p1)
        path.quadTo(ctrl, p2)
        self.setPath(path)
        self._tip, self._from = p2, ctrl
        self._place_label(ctrl)

    def _place_label(self, pos):
        br = self._text.boundingRect()
        self._text.setPos(pos.x() - br.width() / 2.0, pos.y() - br.height() / 2.0)
        pad = 3.0
        self._label_bg.setRect(pos.x() - br.width() / 2.0 - pad,
                               pos.y() - br.height() / 2.0 - pad,
                               br.width() + 2 * pad, br.height() + 2 * pad)

    def boundingRect(self):
        return self.path().boundingRect().adjusted(-24, -24, 24, 24)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)     # the curve
        ang = math.atan2(self._tip.y() - self._from.y(), self._tip.x() - self._from.x())
        size = 12
        tip = self._tip
        left = QtCore.QPointF(tip.x() - size * math.cos(ang - math.radians(24)),
                              tip.y() - size * math.sin(ang - math.radians(24)))
        right = QtCore.QPointF(tip.x() - size * math.cos(ang + math.radians(24)),
                               tip.y() - size * math.sin(ang + math.radians(24)))
        painter.setBrush(EDGE_COLOR)
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
