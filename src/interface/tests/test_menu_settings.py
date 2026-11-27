import unittest
from time import perf_counter
from threading import Event
from pathlib import Path
from uuid import uuid4

from interface.contracts import HandInputState, SettingSpec, SpeechCategory
from interface.menu import MenuItem, MenuNavigator
from interface.menu import MenuItem, MenuNavigator
from interface.settings import SettingsRegistry
from interface.settings_editor import SettingsEditor, SettingsTarget
from interface.audio import AudioService, NullSpeechBackend, SpeechBackend
from interface.lens_controller import LensController
from interface.tactile import ScreenTactileOutput


class MenuSettingsTests(unittest.TestCase):
    def test_interrupting_speech_does_not_kill_audio_worker(self):
        started = Event()
        release = Event()

        class BlockingBackend(SpeechBackend):
            def speak(self, text, interrupt=False):
                started.set()
                release.wait(1.0)

            def stop(self):
                pass

        audio = AudioService(backend=BlockingBackend())
        try:
            audio.speak("first", interrupt=True)
            self.assertTrue(started.wait(1.0))
            audio.speak("second", interrupt=True)
            release.set()
            deadline = perf_counter() + 1.0
            while perf_counter() < deadline and not audio._thread.is_alive():
                pass
            self.assertTrue(audio._thread.is_alive())
        finally:
            release.set()
            audio.close()

    def test_rapid_arrow_navigation_stays_non_blocking(self):
        audio = AudioService(backend=NullSpeechBackend())
        controller = LensController(tactile=ScreenTactileOutput(), audio=audio)
        controller.register(_MenuLens)
        controller.start("test_menu")
        try:
            controller.update(None, HandInputState(timestamp_s=0.0))
            start = perf_counter()
            for index in range(1, 21):
                controller.update(None, HandInputState(
                    joystick=1.0, timestamp_s=float(index)
                ))
                controller.update(None, HandInputState(timestamp_s=float(index) + 0.01))
            elapsed = perf_counter() - start
        finally:
            controller.close()
        self.assertLess(elapsed, 0.25)
    def test_menu_wraps_and_announces_instructions_only_on_entry(self):
        menu = MenuNavigator(
            "Menu", [MenuItem("a", "Alpha"), MenuItem("b", "Bravo")],
            instructions=("Use the joystick.",),
        )
        first = menu.update(HandInputState())
        self.assertEqual(len(first.speech), 1)
        self.assertEqual(first.speech[0].category, SpeechCategory.CONTEXT)
        self.assertIn("Menu. Alpha", first.speech[0].text)
        self.assertIn("Use the joystick.", first.speech[0].instruction_text)

        moved = menu.update(HandInputState(joystick=-1.0, timestamp_s=1.0))
        self.assertEqual(menu.current.key, "b")
        self.assertEqual(len(moved.speech), 1)
        self.assertEqual(moved.speech[0].text, "Bravo")

        wrapped = menu.update(HandInputState(joystick=-1.0, timestamp_s=2.0))
        self.assertEqual(menu.current.key, "a")
        self.assertEqual(wrapped.speech[0].text, "Alpha")

    def test_settings_are_staged_until_save(self):
        registry = SettingsRegistry()
        registry.register_scope("test", (
            SettingSpec("enabled", "Enabled", "bool", False, choices=(False, True),
                        choice_labels=("off", "on")),
        ))
        target = SettingsTarget("test", "Test Settings", registry)
        editor = SettingsEditor(target)

        editor.update(None, HandInputState())
        editor.update(None, HandInputState(button_pressed=True))
        editor.update(None, HandInputState(joystick=1.0, timestamp_s=1.0))
        editor.update(None, HandInputState(button_pressed=True, timestamp_s=2.0))
        self.assertFalse(registry.get("test", "enabled"))
        self.assertEqual(editor.transaction.get("enabled"), True)

        editor.update(None, HandInputState(joystick=1.0, timestamp_s=3.0))
        editor.update(None, HandInputState(joystick=1.0, timestamp_s=4.0))
        editor.update(None, HandInputState(button_pressed=True, timestamp_s=5.0))
        editor.update(None, HandInputState(button_pressed=True, timestamp_s=6.0))
        self.assertTrue(registry.get("test", "enabled"))

    def test_system_settings_persist(self):
        path = Path.cwd() / f".test-settings-{uuid4().hex}.json"
        try:
            first = SettingsRegistry(path)
            first.register_scope("system", (
                SettingSpec("menu_instructions", "Menu instructions", "bool", True),
            ))
            first.set("system", "menu_instructions", False)
            first.commit("system", first.values("system"))

            second = SettingsRegistry(path)
            second.register_scope("system", (
                SettingSpec("menu_instructions", "Menu instructions", "bool", True),
            ))
            self.assertFalse(second.get("system", "menu_instructions"))
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()


class _MenuLens:
    """Small lens fixture used only for the controller timing test."""

    manifest = type("Manifest", (), {
        "lens_id": "test_menu",
        "name": "Test menu",
        "description": "",
        "settings": (),
    })()

    def start(self, context):
        self.menu = MenuNavigator(
            "Test menu", [MenuItem("one", "One"), MenuItem("two", "Two")],
            instructions=("Move the joystick.",),
        )

    def update(self, snapshot, input_state):
        return self.menu.output(self.menu.update(input_state))

    def destroy(self):
        pass
