"""Launch the developer screen UI.

Run from the repository root with:

    PYTHONPATH=src python -m interface.run
"""

import argparse
from pathlib import Path
import sys

from compute.module.camera_feed import CameraFeed as PhysicalCameraFeed
from compute.module.config import load_config
from compute.module.recorded_camera_feed import CameraFeed, recording_by_name
from compute.module.runtime import ComputeRuntime

from .lens_controller import LensController
from .lenses import DevelopmentLens
from .tactile import KeyboardHandInput
from .ui import QApplication, ScreenShell
from .worker import ComputeWorker


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", action="store_true", help="use the physical stereo camera")
    parser.add_argument("--recording", default="", help="recording filename or path")
    parser.add_argument("--svg", default="", help="override the tactile grip SVG path")
    args = parser.parse_args(argv)

    config = load_config()
    if args.recording:
        config["camera"]["recording"] = recording_by_name(args.recording)
    runtime = ComputeRuntime(config)
    feed_class = PhysicalCameraFeed if args.camera else CameraFeed
    worker = ComputeWorker(runtime, feed_class, config["camera"])
    hand_input = KeyboardHandInput()
    controller = LensController()
    controller.register(DevelopmentLens)
    controller.discover_directory(Path(__file__).resolve().parents[1] / "lenses")
    initial_lens = "main-menu" if controller.has_lens("main-menu") else "development"
    controller.start(initial_lens)

    from PySide6.QtWidgets import QApplication as QtApplication
    application = QtApplication(sys.argv)
    svg_path = Path(args.svg) if args.svg else Path(__file__).resolve().parents[1] / "assets" / "grip.svg"
    window = ScreenShell(controller, worker, svg_path, hand_input)
    worker.start()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
