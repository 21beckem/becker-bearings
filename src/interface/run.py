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
from .settings_editor import SettingsLens
from .debug import configure_debug_log
from .tactile import (
    ChannelTactileOutput,
    CombinedHandInput,
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
    parser.add_argument("--debug-log", default="",
                        help="write detailed input/menu/speech diagnostics to this file")
    parser.add_argument("--screen-only", action="store_true",
                        help="disable the physical tactile grip")
    args = parser.parse_args(argv)

    if args.debug_log:
        configure_debug_log(args.debug_log)

    config = load_config()
    if args.recording:
        config["camera"]["recording"] = recording_by_name(args.recording)
    from PySide6.QtWidgets import QApplication as QtApplication
    application = QtApplication(sys.argv)

    runtime = ComputeRuntime(config)
    feed_class = PhysicalCameraFeed if args.camera else CameraFeed
    worker = ComputeWorker(runtime, feed_class, config["camera"])
    screen_output = ScreenTactileOutput()
    if args.screen_only:
        hand_input = KeyboardHandInput()
        tactile_output = screen_output
    else:
        hardware_output = ChannelTactileOutput(
            port=args.tactile_port,
            interval_s=args.tactile_interval,
        )
        tactile_output = MirroredTactileOutput(screen_output, hardware_output)
        hand_input = CombinedHandInput(hardware_output)
    settings_path = Path(__file__).resolve().parents[1] / "compute" / "settings.json"
    from .settings import SettingsRegistry
    controller = LensController(
        tactile=tactile_output,
        settings=SettingsRegistry(settings_path),
        interface_config=config.get("interface", {}),
    )
    controller.register(SettingsLens)
    controller.discover_directory(Path(__file__).resolve().parents[1] / "lenses")
    initial_lens = args.lens if controller.has_lens(args.lens) else "main_menu"
    controller.start(initial_lens)

    svg_path = Path(__file__).resolve().parents[1] / "assets" / "grip.svg"
    window = ScreenShell(controller, worker, svg_path, hand_input)
    worker.start()
    window.show()
    application.aboutToQuit.connect(controller.close)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
