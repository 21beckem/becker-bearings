"""PySide6 developer shell for the compute and lens layers."""

from pathlib import Path

import cv2
import numpy as np

from compute.module.image_tools import ImageTools
from compute.module.map_view import render_finger_rays, render_map

try:
    from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
    from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtWidgets import (
        QApplication, QGridLayout, QLabel, QMainWindow, QVBoxLayout, QWidget,
    )
except ImportError as error:
    raise RuntimeError(
        "The screen UI requires PySide6. Run src/requirements.py first."
    ) from error

from .contracts import HandInputState, TactileState
from .grip_svg import read_grip_points
from .debug import debug


def _image_to_pixmap(image):
    if image is None:
        return QPixmap()
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    else:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    image = np.ascontiguousarray(image)
    height, width, channels = image.shape
    qimage = QImage(image.data, width, height, channels * width, QImage.Format_RGB888)
    return QPixmap.fromImage(qimage.copy())


class ImagePanel(QLabel):
    def __init__(self, title):
        super().__init__()
        self.setObjectName("panel")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(160, 120)
        self.setText(title)
        self._pixmap = QPixmap()

    def set_image(self, image):
        self._pixmap = _image_to_pixmap(image)
        self._refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self):
        if self._pixmap.isNull():
            return
        self.setPixmap(self._pixmap.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))


class TactilePreview(QWidget):
    def __init__(self, svg_path):
        super().__init__()
        self.setObjectName("panel")
        self.renderer = QSvgRenderer(str(svg_path), self)
        self.points = self._read_points(svg_path)
        self.states = (TactileState.OFF,) * 20

    @staticmethod
    def _read_points(svg_path):
        return tuple(QPointF(x, y) for x, y in read_grip_points(svg_path))

    def set_frame(self, frame):
        self.states = frame.points
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bounds = QRectF(self.rect()).adjusted(12, 12, -12, -12)
        viewbox = self.renderer.viewBoxF()
        scale = min(bounds.width() / viewbox.width(), bounds.height() / viewbox.height())
        render_rect = QRectF(0, 0, viewbox.width() * scale, viewbox.height() * scale)
        render_rect.moveCenter(bounds.center())
        self.renderer.render(painter, render_rect)
        for point, state in zip(self.points, self.states):
            x = render_rect.left() + (point.x() - viewbox.left()) * scale
            y = render_rect.top() + (point.y() - viewbox.top()) * scale
            radius = 12 * scale
            color = {
                TactileState.OFF: QColor("#d8d8d8"),
                TactileState.LOW: QColor("#f0b323"),
                TactileState.HIGH: QColor("#50e3a4"),
            }[state]
            painter.setPen(QPen(QColor("#111111"), max(1.0, radius * 0.08)))
            painter.setBrush(color)
            painter.drawEllipse(QPointF(x, y), radius, radius)


class InfoPanel(QLabel):
    def __init__(self):
        super().__init__()
        self.setObjectName("panel")
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setMargin(16)

    def set_output(self, output, audio_error=None):
        lines = [f"<h2>{output.info_title}</h2>"]
        lines.extend(f"<p>{line}</p>" for line in output.info_lines)
        if audio_error:
            lines.append(f"<p><b>Audio error:</b> {audio_error}</p>")
        self.setText("".join(lines))


class StatsPanel(QLabel):
    def __init__(self):
        super().__init__()
        self.setObjectName("footer")
        self.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.setMargin(8)

    def set_snapshot(self, snapshot):
        stats = snapshot.benchmark
        values = []
        for name in ("capture", "depth", "mapping"):
            mean = stats[name]["mean_ms"]
            values.append(f"{name}: {mean:.1f} ms" if mean is not None else f"{name}: --")
        state = "tracking" if snapshot.obstacle_map.tracking_ok else "tracking lost"
        self.setText("  |  ".join(values) + f"  |  {state}  |  frame {snapshot.obstacle_map.integrated_frames}")


class ScreenShell(QMainWindow):
    def __init__(self, controller, worker, svg_path, hand_input):
        super().__init__()
        self.controller = controller
        self.worker = worker
        self.hand_input = hand_input
        self.setWindowTitle("Becker Bearings | tactile lens development UI")
        self.resize(1400, 1000)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QGridLayout(central)
        layout.setSpacing(8)
        self.header = QLabel("Waiting for compute data")
        self.header.setObjectName("header")
        self.header.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.header.setMargin(12)
        self.tactile = TactilePreview(svg_path)
        self.info = InfoPanel()
        self.disparity = ImagePanel("Waiting for disparity map")
        self.lens_view = ImagePanel("Waiting for lens view")
        self.footer = StatsPanel()
        layout.addWidget(self.header, 0, 0, 1, 2)
        layout.addWidget(self.tactile, 1, 0)
        layout.addWidget(self.info, 1, 1)
        layout.addWidget(self.disparity, 2, 0)
        layout.addWidget(self.lens_view, 2, 1)
        layout.addWidget(self.footer, 3, 0, 1, 2)
        layout.setRowStretch(1, 1)
        layout.setRowStretch(2, 1)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        self.setStyleSheet(
            "QMainWindow { background: #101416; color: #eef3f3; }"
            "QLabel#panel, QWidget#panel { background: #20282b; border: 1px solid #506064; }"
            "QLabel#header { background: #263b40; font-size: 20px; }"
            "QLabel#footer { background: #263b40; color: #b9d0d0; }"
        )
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(30)

    def keyPressEvent(self, event):
        key = event.key()
        x = 0.0
        y = 0.0
        if key in (Qt.Key_Left, Qt.Key_A):
            x = -1.0
        elif key in (Qt.Key_Right, Qt.Key_D):
            x = 1.0
        elif key in (Qt.Key_Up, Qt.Key_W):
            y = -1.0
        elif key in (Qt.Key_Down, Qt.Key_S):
            y = 1.0
        if x or y:
            debug("ui_key_press key=%s joystick_x=%s joystick_y=%s", key, x, y)
            self.hand_input.set_state(joystick_x=x, joystick_y=y)
        elif key in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            debug("ui_key_press key=%s button_down=True", key)
            self.hand_input.set_state(button_down=True, button_pressed=True)
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_A, Qt.Key_D,
                   Qt.Key_Up, Qt.Key_Down, Qt.Key_W, Qt.Key_S):
            debug("ui_key_release key=%s", key)
            self.hand_input.set_state(joystick_x=0.0, joystick_y=0.0)
        elif key in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            debug("ui_key_release key=%s button_down=False", key)
            self.hand_input.set_state(button_down=False, button_pressed=False)
        else:
            super().keyReleaseEvent(event)

    def _poll(self):
        if self.worker.error is not None:
            self.header.setText(f"Compute error: {self.worker.error}")
            self.timer.stop()
            return
        snapshot = self.worker.latest()
        if snapshot is None:
            if self.worker.finished:
                self.header.setText("Compute finished")
                self.timer.stop()
            return
        output = self.controller.update(snapshot, self.hand_input.read())
        self.header.setText(output.header_text or self.controller.audio.current_text or " ")
        self.tactile.set_frame(output.tactile)
        self.info.set_output(output, self.controller.audio.last_error)
        self.disparity.set_image(ImageTools.depth_image(snapshot.result))
        if output.view_mode == "camera":
            self.lens_view.set_image(snapshot.result.gray)
        elif output.view_mode == "disparity":
            self.lens_view.set_image(ImageTools.depth_image(snapshot.result))
        elif output.view_mode == "finger_rays" and output.view_payload is not None:
            self.lens_view.set_image(
                render_finger_rays(snapshot.obstacle_map, output.view_payload))
        else:
            self.lens_view.set_image(render_map(snapshot.obstacle_map))
        self.footer.set_snapshot(snapshot)

    def closeEvent(self, event):
        self.timer.stop()
        self.worker.stop()
        self.controller.close()
        self.worker.runtime.finish()
        super().closeEvent(event)
