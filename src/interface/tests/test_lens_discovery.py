import pathlib
import unittest

from interface.contracts import HandInputState
from interface.lens_controller import LensController, discover_lenses
from interface.settings_editor import SettingsLens
from interface.tactile import ScreenTactileOutput


ROOT = pathlib.Path(__file__).resolve().parents[2]


class LensDiscoveryTests(unittest.TestCase):
    def test_main_menu_script_is_discovered(self):
        factories = list(discover_lenses(ROOT / "lenses"))
        self.assertEqual(
            [factory.manifest.lens_id for factory in map(lambda f: f(), factories)],
            ["finger_rays", "main_menu"],
        )

    def test_main_menu_uses_slider_navigation_and_selects_on_button(self):
        class FakeAudio:
            def close(self):
                pass

            def speak(self, *_args, **_kwargs):
                pass

        controller = LensController(tactile=ScreenTactileOutput(), audio=FakeAudio())
        controller.discover_directory(ROOT / "lenses")
        controller.start("main_menu")
        first = controller.update(None, HandInputState())
        selected = controller.update(None, HandInputState(button_down=True, button_pressed=True))
        controller.close()
        self.assertEqual(first.tactile.points[0].value, 2)
        self.assertTrue(any("Main Menu" in request.text for request in first.speech))
        self.assertEqual(selected.tactile.points[0].value, 2)

    def test_main_menu_entry_precedes_instructions_and_option(self):
        class FakeAudio:
            def __init__(self):
                self.calls = []

            def close(self):
                pass

            def speak(self, text, *args, **kwargs):
                self.calls.append(text)

        audio = FakeAudio()
        controller = LensController(tactile=ScreenTactileOutput(), audio=audio)
        controller.discover_directory(ROOT / "lenses")
        controller.start("main_menu")
        controller.update(None, HandInputState())
        controller.close()
        self.assertEqual(
            audio.calls[:3],
            [
                "Entering Main Menu",
                "Move the joystick to slide through menu options. Press the button to select.",
                "Finger Rays",
            ],
        )

    def test_double_button_press_opens_quick_menu_for_any_lens(self):
        class FakeAudio:
            def close(self):
                pass

            def speak(self, *_args, **_kwargs):
                pass

        controller = LensController(tactile=ScreenTactileOutput(), audio=FakeAudio())
        controller.discover_directory(ROOT / "lenses")
        controller.register(SettingsLens)
        controller.start("finger_rays")
        controller.update(None, HandInputState(button_down=True, button_pressed=True,
                                                timestamp_s=1.0))
        controller.update(None, HandInputState(timestamp_s=1.1))
        quick = controller.update(
            None, HandInputState(button_down=True, button_pressed=True, timestamp_s=1.2)
        )
        self.assertEqual(quick.info_title, "Quick menu")
        self.assertEqual(controller.active_lens.manifest.lens_id, "finger_rays")

        controller.update(None, HandInputState(timestamp_s=1.3))
        # Main Menu is the first quick-menu option.
        controller.update(None, HandInputState(timestamp_s=2.0))
        controller.update(None, HandInputState(timestamp_s=2.1))
        controller.update(None, HandInputState(button_down=True, button_pressed=True,
                                                timestamp_s=2.2))
        self.assertEqual(controller.active_lens.manifest.lens_id, "main_menu")
        # Holding the selecting button must not immediately select Main Menu's
        # first item and jump back to Finger Rays.
        controller.update(None, HandInputState(button_down=True, button_pressed=True,
                                                timestamp_s=2.3))
        self.assertEqual(controller.active_lens.manifest.lens_id, "main_menu")

        controller.start("finger_rays")
        controller.update(None, HandInputState(button_down=True, button_pressed=True,
                                                timestamp_s=3.0))
        controller.update(None, HandInputState(timestamp_s=3.1))
        controller.update(None, HandInputState(button_down=True, button_pressed=True,
                                                timestamp_s=3.2))
        controller.update(None, HandInputState(timestamp_s=3.3))
        controller.update(None, HandInputState(joystick=1.0, timestamp_s=4.0))
        controller.update(None, HandInputState(timestamp_s=4.1))
        controller.update(None, HandInputState(button_down=True, button_pressed=True,
                                                timestamp_s=5.2))
        self.assertIsNotNone(controller._quick_menu_editor)
        controller.close()

    def test_entering_a_lens_announces_it(self):
        class FakeAudio:
            def __init__(self):
                self.calls = []

            def close(self):
                pass

            def speak(self, text, *_args, **_kwargs):
                self.calls.append(text)

        audio = FakeAudio()
        controller = LensController(tactile=ScreenTactileOutput(), audio=audio)
        controller.discover_directory(ROOT / "lenses")
        controller.start("finger_rays")
        controller.update(None, HandInputState())
        controller.close()
        self.assertTrue(any("Entering Finger Rays" in text for text in audio.calls))

    def test_quick_menu_entry_and_resume_are_lens_entries(self):
        class FakeAudio:
            def __init__(self):
                self.calls = []

            def close(self):
                pass

            def speak(self, text, *args, **kwargs):
                self.calls.append((text, kwargs))

        audio = FakeAudio()
        controller = LensController(tactile=ScreenTactileOutput(), audio=audio)
        controller.discover_directory(ROOT / "lenses")
        controller.start("finger_rays")
        controller.update(None, HandInputState())

        controller._open_quick_menu()
        controller.update(None, HandInputState(timestamp_s=1.0))
        self.assertTrue(any(text == "Entering Quick menu" for text, _ in audio.calls))

        controller._close_quick_menu()
        controller.update(None, HandInputState(timestamp_s=2.0))
        self.assertTrue(any(text == "Resuming Finger Rays" for text, _ in audio.calls))
        controller.close()


if __name__ == "__main__":
    unittest.main()
