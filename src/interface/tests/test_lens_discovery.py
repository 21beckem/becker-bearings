import pathlib
import unittest

from interface.contracts import HandInputState
from interface.lens_controller import LensController, discover_lenses
from interface.tactile import ScreenTactileOutput


ROOT = pathlib.Path(__file__).resolve().parents[2]


class LensDiscoveryTests(unittest.TestCase):
    def test_main_menu_script_is_discovered(self):
        factories = list(discover_lenses(ROOT / "lenses"))
        self.assertEqual([factory.manifest.lens_id for factory in map(lambda f: f(), factories)], ["main-menu"])

    def test_main_menu_advances_once_per_button_press(self):
        class FakeAudio:
            def close(self):
                pass

            def speak(self, *_args, **_kwargs):
                pass

        controller = LensController(tactile=ScreenTactileOutput(), audio=FakeAudio())
        controller.discover_directory(ROOT / "lenses")
        controller.start("main-menu")
        controller.update(None, HandInputState())
        first = controller.update(None, HandInputState(button_down=True, button_pressed=True))
        held = controller.update(None, HandInputState(button_down=True, button_pressed=True))
        released = controller.update(None, HandInputState())
        second = controller.update(None, HandInputState(button_down=True, button_pressed=True))
        controller.close()
        self.assertEqual(first.tactile.points[0].value, 2)
        self.assertEqual(held.tactile.points[0].value, 2)
        self.assertEqual(released.tactile.points[0].value, 2)
        self.assertEqual(second.tactile.points[1].value, 2)


if __name__ == "__main__":
    unittest.main()
