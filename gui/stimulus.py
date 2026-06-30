"""Stimulus rendering for GUI mode.

StimulusScene holds the current frame (two figures + optional choice overlay) in
a QGraphicsScene. Two views share it: a frameless fullscreen StimulusWindow on
the secondary monitor (what the animal sees) and the middle mirror in the main
window. Render ops arrive from the worker via the Bus and are applied on the Qt
main thread by MainWindow.
"""

import os

from PySide6 import QtCore, QtGui, QtWidgets

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG_DIR = os.path.join(_ROOT, "figures")
FIG_FILES = {
    1: os.path.join(FIG_DIR, "orientation_horizontal.png"),
    2: os.path.join(FIG_DIR, "orientation_vertical.png"),
}
OVERLAY_CORRECT = os.path.join(FIG_DIR, "correct_square.png")
OVERLAY_INCORRECT = os.path.join(FIG_DIR, "incorrect_square.png")


class StimulusScene(QtCore.QObject):
    """Owns a QGraphicsScene and applies show/choice/black ops to it."""

    def __init__(self, highlight_ms=1500, parent=None):
        super().__init__(parent)
        self.scene = QtWidgets.QGraphicsScene()
        self.scene.setBackgroundBrush(QtGui.QColor(0, 0, 0))
        self.scene.setSceneRect(0, 0, 1280, 720)

        self._pix = {k: self._load(p) for k, p in FIG_FILES.items()}
        self._overlay_correct = self._load(OVERLAY_CORRECT)
        self._overlay_incorrect = self._load(OVERLAY_INCORRECT)

        self._cur_l = None
        self._cur_r = None
        self._overlay_side = None
        self._overlay_kind = "correct"      # "correct" (green) | "incorrect" (blue)
        self._pending_black = False
        self.highlight_ms = highlight_ms

        self._overlay_timer = QtCore.QTimer(self)
        self._overlay_timer.setSingleShot(True)
        self._overlay_timer.timeout.connect(self._overlay_expired)

        self._render()

    @staticmethod
    def _load(path):
        if os.path.exists(path):
            pm = QtGui.QPixmap(path)
            if not pm.isNull():
                return pm
        return None

    # ---- ops (called on the main thread) -----------------------------------
    def show(self, left_fig, right_fig):
        self._cur_l = left_fig
        self._cur_r = right_fig
        self._overlay_side = None
        self._pending_black = False
        self._overlay_timer.stop()
        self._render()

    def choice(self, side, correct=True):
        self._overlay_side = "L" if str(side).upper() == "LEFT" else "R"
        self._overlay_kind = "correct" if correct else "incorrect"
        self._render()
        self._overlay_timer.start(self.highlight_ms)

    def black(self):
        if self._overlay_side:
            self._pending_black = True
        else:
            self._cur_l = self._cur_r = None
            self._render()

    def _overlay_expired(self):
        self._overlay_side = None
        if self._pending_black:
            self._cur_l = self._cur_r = None
            self._pending_black = False
        self._render()

    # ---- drawing -----------------------------------------------------------
    def _overlay_pixmap(self):
        return (self._overlay_incorrect if self._overlay_kind == "incorrect"
                else self._overlay_correct)

    def _render(self):
        self.scene.clear()
        rect = self.scene.sceneRect()
        w, h = rect.width(), rect.height()
        ov = self._overlay_pixmap()
        # A side is drawn if it has a figure OR an overlay flashing on it. Only
        # when neither side has anything is the whole screen black.
        left_on = bool(self._cur_l) or self._overlay_side == "L"
        right_on = bool(self._cur_r) or self._overlay_side == "R"
        if not left_on and not right_on:
            return
        gap = w * 0.04
        half = (w - gap) / 2.0
        max_h = h * 0.9
        if left_on:
            self._place(self._pix.get(self._cur_l) if self._cur_l else None,
                        half / 2.0, h / 2.0, half, max_h,
                        ov if self._overlay_side == "L" else None)
        if right_on:
            self._place(self._pix.get(self._cur_r) if self._cur_r else None,
                        half + gap + half / 2.0, h / 2.0, half, max_h,
                        ov if self._overlay_side == "R" else None)

    def _place(self, pm, cx, cy, max_w, max_h, overlay):
        if pm is not None and not pm.isNull():
            scaled = pm.scaled(int(max_w), int(max_h), QtCore.Qt.KeepAspectRatio,
                               QtCore.Qt.SmoothTransformation)
            item = QtWidgets.QGraphicsPixmapItem(scaled)
            item.setOffset(cx - scaled.width() / 2.0, cy - scaled.height() / 2.0)
            self.scene.addItem(item)
        # The correct (green) / incorrect (blue) square is always the SAME size —
        # a square fitted to the half-region — whether or not a figure is present,
        # so the two never look different sizes.
        if overlay is not None and not overlay.isNull():
            side = int(min(max_w, max_h))
            sq = overlay.scaled(side, side, QtCore.Qt.KeepAspectRatio,
                                QtCore.Qt.SmoothTransformation)
            ovi = QtWidgets.QGraphicsPixmapItem(sq)
            ovi.setOffset(cx - sq.width() / 2.0, cy - sq.height() / 2.0)
            self.scene.addItem(ovi)


class _FitView(QtWidgets.QGraphicsView):
    """A view that keeps the whole scene fitted on resize."""

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QtGui.QColor(0, 0, 0))

    def resizeEvent(self, event):
        self.fitInView(self.sceneRect(), QtCore.Qt.KeepAspectRatio)
        super().resizeEvent(event)

    def showEvent(self, event):
        self.fitInView(self.sceneRect(), QtCore.Qt.KeepAspectRatio)
        super().showEvent(event)


class MirrorView(_FitView):
    """Small live mirror of the stimulus, shown in the middle panel."""
    pass


class StimulusWindow(_FitView):
    """Frameless fullscreen window that shows the stimulus on a chosen monitor."""

    closed = QtCore.Signal()

    def __init__(self, scene):
        super().__init__(scene)
        self.setWindowTitle("Stimulus")
        self.setFrameShape(QtWidgets.QFrame.NoFrame)

    def open_on_screen(self, screen_index):
        screens = QtWidgets.QApplication.screens()
        if 0 <= screen_index < len(screens):
            geo = screens[screen_index].geometry()
            self.setGeometry(geo)
            self.showFullScreen()
            # ensure it lands on the right screen
            handle = self.windowHandle()
            if handle is not None:
                handle.setScreen(screens[screen_index])
            self.setGeometry(geo)
            self.showFullScreen()
        else:
            self.resize(960, 540)
            self.show()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)
