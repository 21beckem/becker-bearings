import pathlib
import unittest

from interface.contracts import (
    HandInputState, Lens, LensManifest, LensOutput, SettingSpec,
    TactileFrame, TactileState,
)
from interface.lens_controller import LensController, discover_lenses
from interface.settings_editor import SettingsLens
from interface.tactile import ScreenTactileOutput
from lenses.main_menu import MainMenuLens


ROOT = pathlib.Path(__file__).resolve().parents[2]


class LensDiscoveryTests(unittest.TestCase):
    def test_main_menu_script_is_discovered(self):
        factories = list(discover_lenses(ROOT / "lenses"))
        self.assertEqual(
            [factory.manifest.lens_id for factory in map(lambda f: f(), factories)],
            ["animator", "finger_rays", "main_menu"],
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
        self.assertEqual(first.tactile, TactileFrame.off())
        ready = controller.update(None, HandInputState())
        selected = controller.update(
            None, HandInputState(button_down=True, button_pressed=True)
        )
        controller.close()
        self.assertEqual(ready.tactile.points[0].value, 2)
        self.assertTrue(any("Main Menu" in request.text for request in first.speech))
        self.assertEqual(selected.tactile, TactileFrame.off())

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
                "Animator",
            ],
        )

    def test_entry_barrier_does_not_replay_entry_audio_each_poll(self):
        class BlockingAudio:
            def __init__(self):
                self.calls = []
                self.active = set()

            def close(self):
                pass

            def speak(self, text, *args, **kwargs):
                self.calls.append(text)
                self.active.add(kwargs["message_id"])

            def has_message(self, message_id):
                return message_id in self.active

        audio = BlockingAudio()
        controller = LensController(tactile=ScreenTactileOutput(), audio=audio)
        controller.discover_directory(ROOT / "lenses")
        controller.start("main_menu")

        first = controller.update(None, HandInputState())
        second = controller.update(None, HandInputState())
        third = controller.update(None, HandInputState())

        self.assertEqual(first.tactile, TactileFrame.off())
        self.assertEqual(second.tactile, TactileFrame.off())
        self.assertEqual(third.tactile, TactileFrame.off())
        self.assertEqual(audio.calls.count("Entering Main Menu"), 1)
        controller.close()

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

    def test_quick_menu_settings_and_value_use_successive_columns(self):
        class FakeAudio:
            def close(self):
                pass

            def speak(self, *_args, **_kwargs):
                pass

        controller = LensController(tactile=ScreenTactileOutput(), audio=FakeAudio())
        controller.register(_SettingsCapableLens)
        controller.register(SettingsLens)
        controller.start("settings_capable")
        controller.update(None, HandInputState())
        controller.update(None, HandInputState())

        controller._open_quick_menu()
        controller._quick_menu.index = 1
        controller._select_quick_menu_item("lens_settings")
        controller.update(None, HandInputState())
        settings_output = controller.update(None, HandInputState())
        self.assertEqual(settings_output.tactile.points[1], TactileState.LOW)
        self.assertEqual(settings_output.tactile.points[5], TactileState.HIGH)

        editor = controller._quick_menu_editor
        editor._open_value(editor.target.registry.specs("settings_capable")[0])
        value_output = controller.update(None, HandInputState())
        self.assertEqual(value_output.tactile.points[1], TactileState.LOW)
        self.assertEqual(value_output.tactile.points[5], TactileState.LOW)
        self.assertEqual(value_output.tactile.points[10], TactileState.HIGH)
        controller.close()

    def test_main_menu_settings_preserves_main_menu_column(self):
        class FakeAudio:
            def close(self):
                pass

            def speak(self, *_args, **_kwargs):
                pass

        controller = LensController(tactile=ScreenTactileOutput(), audio=FakeAudio())
        controller.register(MainMenuLens)
        controller.register(_SettingsCapableLens)
        controller.register(SettingsLens)
        controller.start("main_menu")
        controller.update(None, HandInputState())
        controller.update(None, HandInputState())

        main_menu = controller.active_lens
        main_menu.menu.index = next(
            index for index, item in enumerate(main_menu.menu.items)
            if item.key == "settings"
        )
        main_menu.menu.current.select()
        controller.update(None, HandInputState())
        settings_output = controller.update(None, HandInputState())

        self.assertEqual(settings_output.tactile.points[1], TactileState.LOW)
        self.assertEqual(settings_output.tactile.points[5], TactileState.HIGH)
        controller.close()


class _SettingsCapableLens(Lens):
    manifest = LensManifest(
        "settings_capable", "Settings Capable", "",
        settings=(SettingSpec(
            "enabled", "Enabled", "bool", False,
            choices=(False, True), choice_labels=("off", "on"),
        ),),
    )

    def update(self, snapshot, input_state):
        return LensOutput()


if __name__ == "__main__":
    unittest.main()
