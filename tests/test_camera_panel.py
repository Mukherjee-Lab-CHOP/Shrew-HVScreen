import unittest
from unittest.mock import patch

from PySide6 import QtCore, QtMultimedia, QtWidgets

from gui.camera_panel import CameraPanel


class FakeDevice:
    def __init__(self, name, device_id):
        self.name = name
        self.device_id = QtCore.QByteArray(device_id)

    def description(self):
        return self.name

    def id(self):
        return self.device_id


class FakeDevices(QtCore.QObject):
    videoInputsChanged = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self.inputs = [
            FakeDevice("TIOGen5 camera", b"integrated"),
            FakeDevice("WBC-0E01", b"usb"),
        ]

    def videoInputs(self):
        return self.inputs


class FakeCamera(QtCore.QObject):
    Error = QtMultimedia.QCamera.Error
    errorOccurred = QtCore.Signal(object, str)
    activeChanged = QtCore.Signal(bool)

    def __init__(self, device, parent):
        super().__init__(parent)
        self.device = device
        self.started = False
        self.stopped = False

    def cameraDevice(self):
        return self.device

    def start(self):
        self.started = True
        self.activeChanged.emit(True)

    def stop(self):
        self.stopped = True
        self.activeChanged.emit(False)


class FakeSession:
    def __init__(self, parent):
        self.camera = None

    def setVideoOutput(self, output):
        self.output = output

    def setCamera(self, camera):
        self.camera = camera


class CameraPanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.devices = FakeDevices()
        for name, replacement in (
            ("QMediaDevices", lambda parent: self.devices),
            ("QCamera", FakeCamera),
            ("QMediaCaptureSession", FakeSession),
        ):
            patcher = patch(f"gui.camera_panel.QtMultimedia.{name}", replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.panel = CameraPanel()
        self.messages = []
        self.panel.message.connect(self.messages.append)
        self.addCleanup(self.panel.deleteLater)
        self.addCleanup(self.panel.shutdown)

    def test_preview_is_off_initially(self):
        self.assertIsNone(self.panel._camera)
        self.assertEqual(self.panel.selector.count(), 2)
        self.assertTrue(self.panel.start_btn.isEnabled())
        self.assertFalse(self.panel.stop_btn.isEnabled())
        self.assertIs(self.panel.preview.currentWidget(), self.panel.placeholder)

    def test_rotation_reverses_both_axes_and_can_be_disabled(self):
        view = self.panel.video
        view._set_video_size(QtCore.QSizeF(640, 480))
        self.assertTrue(self.panel.rotate_checkbox.isChecked())
        self.assertEqual(view.video_item.rotation(), 180)
        self.assertEqual(view.video_item.mapToScene(QtCore.QPointF(0, 0)),
                         QtCore.QPointF(640, 480))
        self.assertEqual(view.video_item.mapToScene(QtCore.QPointF(640, 480)),
                         QtCore.QPointF(0, 0))
        self.panel.rotate_checkbox.setChecked(False)
        self.assertEqual(view.video_item.rotation(), 0)
        self.assertEqual(view.video_item.mapToScene(QtCore.QPointF(0, 0)),
                         QtCore.QPointF(0, 0))
        self.panel.rotate_checkbox.setChecked(True)
        self.assertEqual(view.video_item.rotation(), 180)

    def test_rotation_survives_resolution_changes_and_preview_restart(self):
        self.panel.rotate_checkbox.setChecked(True)
        self.panel.video._set_video_size(QtCore.QSizeF(1280, 720))
        self.assertEqual(self.panel.video.video_item.mapToScene(QtCore.QPointF(0, 0)),
                         QtCore.QPointF(1280, 720))
        self.panel.start_preview()
        camera = self.panel._camera
        self.panel.rotate_checkbox.setChecked(False)
        self.panel.rotate_checkbox.setChecked(True)
        self.assertIs(self.panel._camera, camera)
        self.assertFalse(camera.stopped)
        self.panel.stop_preview()
        self.panel.start_preview()
        self.assertTrue(self.panel.rotate_checkbox.isChecked())
        self.assertEqual(self.panel.video.video_item.rotation(), 180)

    def test_video_fits_viewport_after_resize_with_rotation(self):
        self.panel.show()
        self.panel.preview.setCurrentWidget(self.panel.video)
        self.panel.video._set_video_size(QtCore.QSizeF(640, 480))
        self.panel.rotate_checkbox.setChecked(True)
        for width, height in ((800, 700), (600, 400)):
            self.panel.resize(width, height)
            self.app.processEvents()
            view = self.panel.video
            rect = view.mapFromScene(view.video_item.sceneBoundingRect()).boundingRect()
            self.assertLessEqual(rect.width(), view.viewport().width())
            self.assertLessEqual(rect.height(), view.viewport().height())
            self.assertAlmostEqual(view.transform().m11(), view.transform().m22())
        self.panel.hide()

    def test_selected_camera_starts_and_live_status_requires_a_frame(self):
        self.panel.selector.setCurrentIndex(1)
        self.panel.start_preview()
        camera = self.panel._camera
        self.assertEqual(camera.cameraDevice().description(), "WBC-0E01")
        self.assertTrue(camera.started)
        self.assertIs(self.panel._session.camera, camera)
        self.assertFalse(self.panel.selector.isEnabled())
        self.assertTrue(self.panel._startup_timer.isActive())
        self.assertIn("Starting", self.panel.status.text())
        invalid = QtMultimedia.QVideoFrame()
        self.panel._on_frame(invalid)
        self.assertFalse(self.panel._preview_ready)
        valid = QtMultimedia.QVideoFrame(QtMultimedia.QVideoFrameFormat(
            QtCore.QSize(32, 32),
            QtMultimedia.QVideoFrameFormat.PixelFormat.Format_BGRA8888))
        self.panel._on_frame(valid)
        self.assertTrue(self.panel._preview_ready)
        self.assertIs(self.panel.preview.currentWidget(), self.panel.video)
        self.assertIn("Live: WBC-0E01", self.panel.status.text())
        self.assertFalse(self.panel._startup_timer.isActive())
        self.panel.stop_preview()
        self.assertTrue(camera.stopped)
        self.assertIsNone(self.panel._session.camera)
        self.assertIsNone(self.panel._camera)
        self.assertTrue(self.panel.start_btn.isEnabled())
        self.assertIs(self.panel.preview.currentWidget(), self.panel.placeholder)

    def test_no_camera_disables_start_and_reports_missing_device(self):
        self.devices.inputs = []
        self.panel.refresh_devices()
        self.assertFalse(self.panel.start_btn.isEnabled())
        self.assertIn("No camera detected", self.panel.status.text())
        self.panel.start_preview()
        self.assertIsNone(self.panel._camera)
        self.assertTrue(any("unavailable" in message for message in self.messages))

    def test_refresh_retains_selection_by_device_id(self):
        self.panel.selector.setCurrentIndex(1)
        self.devices.inputs.reverse()
        self.panel.refresh_devices()
        self.assertEqual(self.panel.selector.currentText(), "WBC-0E01")

    def test_hot_unplug_releases_camera_and_reports_disconnect(self):
        self.panel.selector.setCurrentIndex(1)
        self.panel.start_preview()
        camera = self.panel._camera
        self.devices.inputs.pop()
        self.devices.videoInputsChanged.emit()
        self.assertTrue(camera.stopped)
        self.assertIsNone(self.panel._camera)
        self.assertIn("disconnected", self.panel.status.text())
        self.assertTrue(self.panel.start_btn.isEnabled())

    def test_error_releases_camera_and_allows_retry(self):
        self.panel.start_preview()
        camera = self.panel._camera
        camera.errorOccurred.emit(QtMultimedia.QCamera.Error.CameraError, "Access denied")
        self.assertTrue(camera.stopped)
        self.assertIsNone(self.panel._camera)
        self.assertTrue(self.panel.start_btn.isEnabled())
        self.assertIn("Access denied", self.panel.status.text())
        self.assertIn("permissions", self.messages[-1])
        self.panel.start_preview()
        self.assertIsNotNone(self.panel._camera)

    def test_timeout_reports_missing_frames(self):
        self.panel.start_preview()
        self.panel._startup_timeout()
        self.assertIsNone(self.panel._camera)
        self.assertIn("No camera frames", self.panel.status.text())

    def test_unexpected_stop_reports_failure(self):
        self.panel.start_preview()
        self.panel._camera.activeChanged.emit(False)
        self.assertIsNone(self.panel._camera)
        self.assertIn("unexpectedly", self.panel.status.text())

    def test_shutdown_releases_camera_and_ignores_late_frames(self):
        self.panel.start_preview()
        camera = self.panel._camera
        self.panel.shutdown()
        self.panel.shutdown()
        self.panel._on_frame(QtMultimedia.QVideoFrame())
        self.assertTrue(camera.stopped)
        self.assertIsNone(self.panel._session.camera)
        self.assertFalse(self.panel._startup_timer.isActive())
        self.assertFalse(self.panel._preview_ready)


if __name__ == "__main__":
    unittest.main()
