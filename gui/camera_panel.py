"""Optional camera preview, independent of experiment and serial control."""

from PySide6 import QtCore, QtMultimedia, QtMultimediaWidgets, QtWidgets


class CameraView(QtWidgets.QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        scene = QtWidgets.QGraphicsScene(self)
        self.setScene(scene)
        self.video_item = QtMultimediaWidgets.QGraphicsVideoItem()
        self.video_item.setAspectRatioMode(QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        scene.addItem(self.video_item)
        self.setBackgroundBrush(QtCore.Qt.GlobalColor.black)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.video_item.nativeSizeChanged.connect(self._set_video_size)

    def _set_video_size(self, size):
        if size.isEmpty():
            return
        self.video_item.setSize(size)
        self.video_item.setTransformOriginPoint(self.video_item.boundingRect().center())
        self._fit_video()

    def set_upside_down(self, enabled):
        self.video_item.setRotation(180 if enabled else 0)
        self._fit_video()

    def _fit_video(self):
        rect = self.video_item.sceneBoundingRect()
        self.setSceneRect(rect)
        self.fitInView(rect, QtCore.Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_video()


class CameraPanel(QtWidgets.QWidget):
    message = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._camera = None
        self._preview_ready = False
        self._devices = QtMultimedia.QMediaDevices(self)
        self._session = QtMultimedia.QMediaCaptureSession(self)
        self._startup_timer = QtCore.QTimer(self)
        self._startup_timer.setSingleShot(True)
        self._startup_timer.setInterval(10000)
        self._startup_timer.timeout.connect(self._startup_timeout)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QtWidgets.QLabel("<b>Camera (live preview only)</b>"))
        controls = QtWidgets.QHBoxLayout()
        self.selector = QtWidgets.QComboBox()
        self.selector.setToolTip("Select a camera connected to this computer")
        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        self.start_btn = QtWidgets.QPushButton("Start preview")
        self.stop_btn = QtWidgets.QPushButton("Stop preview")
        self.stop_btn.setEnabled(False)
        controls.addWidget(self.selector, 1)
        controls.addWidget(self.refresh_btn)
        controls.addWidget(self.start_btn)
        controls.addWidget(self.stop_btn)
        layout.addLayout(controls)
        self.rotate_checkbox = QtWidgets.QCheckBox("Rotate 180 degrees")
        self.rotate_checkbox.setToolTip("Correct an upside-down camera image; preview only")
        layout.addWidget(self.rotate_checkbox)

        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.video = CameraView()
        self.placeholder = QtWidgets.QLabel("Camera preview is off")
        self.placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setStyleSheet("background: black; color: white;")
        self.preview = QtWidgets.QStackedWidget()
        self.preview.setMinimumHeight(180)
        self.preview.addWidget(self.placeholder)
        self.preview.addWidget(self.video)
        layout.addWidget(self.preview, 1)
        self._session.setVideoOutput(self.video.video_item)
        self.video.video_item.videoSink().videoFrameChanged.connect(self._on_frame)
        self.rotate_checkbox.toggled.connect(self.video.set_upside_down)
        self.rotate_checkbox.setChecked(True)

        self.refresh_btn.clicked.connect(self.refresh_devices)
        self.start_btn.clicked.connect(self.start_preview)
        self.stop_btn.clicked.connect(self.stop_preview)
        self._devices.videoInputsChanged.connect(self.refresh_devices)
        self.refresh_devices()

    def _set_status(self, text):
        self.status.setText(text)
        self.message.emit(f"[camera] {text}")

    def refresh_devices(self):
        previous_id = self.selector.currentData()
        devices = self._devices.videoInputs()
        if self._camera is not None:
            current_id = self._camera.cameraDevice().id()
            if not any(device.id() == current_id for device in devices):
                self._fail("Camera disconnected. Reconnect it, then start preview again.")
        self.selector.clear()
        for device in devices:
            self.selector.addItem(device.description(), device.id())
        index = self.selector.findData(previous_id)
        if index >= 0:
            self.selector.setCurrentIndex(index)
        running = self._camera is not None
        self.selector.setEnabled(bool(devices) and not running)
        self.start_btn.setEnabled(bool(devices) and not running)
        if not devices:
            self._set_status("No camera detected. Connect a camera and click Refresh.")
        elif not running and not previous_id:
            self._set_status("Select a camera, then click Start preview. No video is recorded.")

    def start_preview(self):
        if self._camera is not None:
            return
        selected_id = self.selector.currentData()
        device = next((d for d in self._devices.videoInputs()
                       if d.id() == selected_id), None)
        if device is None:
            self._set_status("Selected camera is unavailable. Click Refresh and select a camera.")
            self.refresh_devices()
            return
        self._preview_ready = False
        self._camera = QtMultimedia.QCamera(device, self)
        self._camera.errorOccurred.connect(self._on_error)
        self._camera.activeChanged.connect(self._on_active_changed)
        self._session.setCamera(self._camera)
        self.selector.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._set_status(f"Starting {device.description()}...")
        self._startup_timer.start()
        self._camera.start()

    def stop_preview(self):
        self._release_camera()
        self._set_status("Camera preview stopped. No video was recorded.")

    def shutdown(self):
        self._release_camera()

    def _release_camera(self):
        self._startup_timer.stop()
        camera = self._camera
        self._camera = None
        self._preview_ready = False
        if camera is not None:
            camera.errorOccurred.disconnect(self._on_error)
            camera.activeChanged.disconnect(self._on_active_changed)
            camera.stop()
            self._session.setCamera(None)
            camera.deleteLater()
        self.preview.setCurrentWidget(self.placeholder)
        available = self.selector.count() > 0
        self.selector.setEnabled(available)
        self.start_btn.setEnabled(available)
        self.stop_btn.setEnabled(False)

    def _on_frame(self, frame):
        if self._camera is None or self._preview_ready or not frame.isValid():
            return
        self._preview_ready = True
        self._startup_timer.stop()
        self.preview.setCurrentWidget(self.video)
        self._set_status(f"Live: {self._camera.cameraDevice().description()} (not recording)")

    def _on_active_changed(self, active):
        if not active and self._camera is not None:
            self._fail("Camera preview stopped unexpectedly. Check the connection and try again.")

    def _on_error(self, error, text):
        if error != QtMultimedia.QCamera.Error.NoError and self._camera is not None:
            self._fail(f"Camera error: {text}. Check Windows camera permissions "
                       "and close other apps using the camera.")

    def _startup_timeout(self):
        if self._camera is not None:
            self._fail("No camera frames received. Check Windows camera permissions "
                       "and close other apps using the camera, then try again.")

    def _fail(self, text):
        self._release_camera()
        self._set_status(text)
