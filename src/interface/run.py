"""Launch the developer screen UI.

Run from the repository root with ``begin.bat``.
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
from .tactile import (
    ChannelTactileOutput,
    KeyboardHandInput,
    MirroredTactileOutput,
    ScreenTactileOutput,
)
from .ui import QApplication, ScreenShell
from .worker import ComputeWorker


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", action="store_true", help="use the physical stereo camera")
    parser.add_argument("--recording", default="", help="recording filename or path")
    parser.add_argument("--tactile-port", default="COM4", help="serial port for the tactile grip")
    parser.add_argument("--tactile-interval", type=float, default=0.01,
                        help="seconds between tactile hardware updates")
    parser.add_argument("--lens", default="main_menu", help="the initial lens to load (default: main_menu)")
    parser.add_argument("--screen-only", action="store_true",
                        help="disable the physical tactile grip")
    args = parser.parse_args(argv)

    config = load_config()
    if args.recording:
        config["camera"]["recording"] = recording_by_name(args.recording)
    from PySide6.QtWidgets import QApplication as QtApplication
    application = QtApplication(sys.argv)

    runtime = ComputeRuntime(config)
    feed_class = PhysicalCameraFeed if args.camera else CameraFeed
    worker = ComputeWorker(runtime, feed_class, config["camera"])
    hand_input = KeyboardHandInput()
    screen_output = ScreenTactileOutput()
    if args.screen_only:
        tactile_output = screen_output
    else:
        hardware_output = ChannelTactileOutput(
            port=args.tactile_port,
            interval_s=args.tactile_interval,
        )
        tactile_output = MirroredTactileOutput(screen_output, hardware_output)
    controller = LensController(tactile=tactile_output)
    controller.register(DevelopmentLens)
    controller.discover_directory(Path(__file__).resolve().parents[1] / "lenses")
    initial_lens = args.lens if controller.has_lens(args.lens) else "development"
    controller.start(initial_lens)

    svg_path = Path(__file__).resolve().parents[1] / "assets" / "grip.svg"
    window = ScreenShell(controller, worker, svg_path, hand_input)
    worker.start()
    window.show()
    application.aboutToQuit.connect(controller.close)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
