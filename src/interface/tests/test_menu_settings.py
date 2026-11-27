import unittest
from time import perf_counter
from threading import Event
from pathlib import Path
from uuid import uuid4

from interface.contracts import (
    HandInputState, LensOutput, SettingSpec, SpeechCategory,
    SpeechMessageType, SpeechRequest, TactileFrame, TactileState,
)
from interface.menu import MenuItem, MenuNavigator, MenuStack
from interface.settings import SettingsRegistry
from interface.settings_editor import SettingsEditor, SettingsTarget
from interface.audio import AudioService, NullSpeechBackend, SpeechBackend
from interface.lens_controller import LensController
from interface.tactile import ScreenTactileOutput


class MenuSettingsTests(unittest.TestCase):
    def test_menu_stack_places_parent_and_current_layers_in_columns(self):
        parent = MenuNavigator(
            "Parent", [MenuItem("a", "A"), MenuItem("b", "B")],
        )
        parent.index = 1
        current = MenuNavigator(
            "Current", [MenuItem("x", "X"), MenuItem("y", "Y")],
        )
        current.index = 0

        frame = MenuStack((parent, current), "trinary_ancestors_low").frame()

        self.assertEqual(frame.points[1], TactileState.LOW)
        self.assertEqual(frame.points[5], TactileState.HIGH)

    def test_menu_stack_supports_binary_and_current_only_modes(self):
        parent = MenuNavigator("Parent", [MenuItem("a", "A")])
        current = MenuNavigator("Current", [MenuItem("x", "X")])

        binary = MenuStack((parent, current), "binary_ancestors_high").frame()
        current_only = MenuStack((parent, current), "current_only").frame()

        self.assertEqual(binary.points[0], TactileState.HIGH)
        self.assertEqual(binary.points[5], TactileState.HIGH)
        self.assertEqual(current_only.points[0], TactileState.OFF)
        self.assertEqual(current_only.points[5], TactileState.HIGH)

    def test_long_menu_pages_across_the_five_positions(self):
        menu = MenuNavigator(
            "Long", [MenuItem(str(index), str(index)) for index in range(7)],
        )
        menu.index = 5

        frame = MenuStack((menu,)).frame()

        self.assertEqual(frame.points[0], TactileState.HIGH)
        self.assertEqual(frame.points[4], TactileState.OFF)

    def test_known_phrase_plays_clip_without_calling_tts_backend(self):
        class RecordingBackend(SpeechBackend):
            def __init__(self):
                self.calls = []
                self.called = Event()

            def speak(self, text, interrupt=False):
                self.calls.append((text, interrupt))
                self.called.set()

        class RecordingClipPlayer:
            def __init__(self):
                self.calls = []
                self.called = Event()

            def clip_for_text(self, text):
                return "menu.settings" if text == "Settings" else None

            def play_clip(self, clip_id, interrupt=True):
                self.calls.append((clip_id, interrupt))
                self.called.set()
                return clip_id == "menu.settings"

            def close(self):
                pass

        backend = RecordingBackend()
        clips = RecordingClipPlayer()
        audio = AudioService(backend=backend, clip_player=clips)
        try:
            audio.speak("Settings", interrupt=True)
            self.assertTrue(clips.called.wait(1.0))
            audio.speak("dynamic text", interrupt=True)
            self.assertTrue(backend.called.wait(1.0))
        finally:
            audio.close()
        self.assertEqual(clips.calls, [("menu.settings", False)])
        self.assertEqual(backend.calls, [("dynamic text", False)])

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
        self.assertEqual(len(first.speech), 2)
        self.assertEqual(first.speech[0].message_type, SpeechMessageType.INSTRUCTION)
        self.assertEqual(first.speech[0].text, "Use the joystick.")
        self.assertEqual(first.speech[1].category, SpeechCategory.OPTION)
        self.assertEqual(first.speech[1].message_type, SpeechMessageType.MENU_OPTION)
        self.assertEqual(first.speech[1].text, "Alpha")

        moved = menu.update(HandInputState(joystick=-1.0, timestamp_s=1.0))
        self.assertEqual(menu.current.key, "b")
        self.assertEqual(len(moved.speech), 1)
        self.assertEqual(moved.speech[0].text, "Bravo")

        wrapped = menu.update(HandInputState(joystick=-1.0, timestamp_s=2.0))
        self.assertEqual(menu.current.key, "a")
        self.assertEqual(wrapped.speech[0].text, "Alpha")

    def test_settings_apply_immediately_after_confirmation(self):
        registry = SettingsRegistry()
        registry.register_scope("test", (
            SettingSpec("enabled", "Enabled", "bool", False,
                        description="Controls the test setting."),
        ))
        target = SettingsTarget("test", "Test Settings", registry)
        editor = SettingsEditor(target)

        editor.update(None, HandInputState())
        editor.update(None, HandInputState(button_pressed=True))
        editor.update(None, HandInputState(joystick=1.0, timestamp_s=1.0))
        confirmation = editor.update(
            None, HandInputState(button_pressed=True, timestamp_s=2.0)
        )
        self.assertFalse(registry.get("test", "enabled"))
        self.assertEqual(confirmation.speech[0].text,
                         "Change enabled from off to on?")

        result = editor.update(
            None, HandInputState(button_pressed=True, timestamp_s=4.0)
        )
        self.assertTrue(registry.get("test", "enabled"))
        self.assertEqual(result.speech[0].text,
                         "Enabled changed from off to on.")
        self.assertEqual(editor.update(None, HandInputState()).speech, ())
        self.assertEqual(
            editor.update(None, HandInputState()).speech[0].text,
            "Enabled currently on",
        )

    def test_cancel_keeps_setting_unchanged(self):
        registry = SettingsRegistry()
        registry.register_scope("test", (
            SettingSpec("enabled", "Enabled", "bool", False),
        ))
        editor = SettingsEditor(SettingsTarget("test", "Test Settings", registry))

        editor.update(None, HandInputState())
        editor.update(None, HandInputState(button_pressed=True))
        editor.update(None, HandInputState(joystick=1.0, timestamp_s=1.0))
        editor.update(None, HandInputState(button_pressed=True, timestamp_s=2.0))
        editor.update(None, HandInputState(joystick=-1.0, timestamp_s=2.5))
        editor.update(None, HandInputState(button_pressed=True, timestamp_s=3.0))

        self.assertFalse(registry.get("test", "enabled"))
        self.assertIn("Edit canceled", editor._last_output.speech[0].text)
        self.assertEqual(editor.update(None, HandInputState()).speech, ())
        self.assertEqual(
            editor.update(None, HandInputState()).speech[0].text,
            "Enabled currently off",
        )

    def test_info_action_requires_a_generated_clip(self):
        registry = SettingsRegistry()
        registry.register_scope("test", (
            SettingSpec("enabled", "Enabled", "bool", False,
                        description="Controls the test setting."),
        ))
        editor = SettingsEditor(SettingsTarget("test", "Test Settings", registry))

        editor.update(None, HandInputState())
        editor.update(None, HandInputState(button_pressed=True))
        editor.update(None, HandInputState(joystick=1.0, timestamp_s=1.0))
        editor.update(None, HandInputState(joystick=1.0, timestamp_s=2.0))
        info_output = editor.update(
            None, HandInputState(button_pressed=True, timestamp_s=3.0)
        )

        info = info_output.speech[0]
        self.assertEqual(info.text, "Controls the test setting.")
        self.assertFalse(info.audio_parts[0].allow_tts)
        self.assertEqual(
            info.audio_parts[0].clip_id,
            "settings.info.test.enabled.description",
        )

    def test_setting_actions_use_generated_audio_parts(self):
        registry = SettingsRegistry()
        registry.register_scope("test", (
            SettingSpec("enabled", "Enabled", "bool", False),
        ))
        editor = SettingsEditor(SettingsTarget("test", "Test Settings", registry))

        editor.update(None, HandInputState())
        editor.update(None, HandInputState(button_pressed=True))
        leave = editor.edit_menu.current.audio_parts()
        self.assertEqual(
            [part.clip_id for part in leave],
            ["settings.action.leave.off"],
        )
        self.assertTrue(all(not part.allow_tts for part in leave))

        turned_on = editor.update(
            None, HandInputState(joystick=1.0, timestamp_s=1.0)
        ).speech[0]
        self.assertEqual(
            [part.clip_id for part in turned_on.audio_parts],
            ["settings.action.turn.on"],
        )

    def test_boolean_values_are_spoken_as_on_and_off(self):
        spec = SettingSpec(
            "enabled", "Enabled", "bool", False,
        )
        self.assertEqual(SettingsEditor._format(spec, False), "off")
        self.assertEqual(SettingsEditor._format(spec, True), "on")

    def test_setting_result_blocks_tactile_feedback_until_audio_finishes(self):
        class BlockingAudio:
            def __init__(self):
                self.active = set()

            def speak(self, text, **kwargs):
                self.active.add(kwargs["message_id"])

            def has_message(self, message_id):
                return message_id in self.active

            def close(self):
                pass

        audio = BlockingAudio()
        controller = LensController(tactile=ScreenTactileOutput(), audio=audio)
        try:
            output = controller._deliver(LensOutput(
                tactile=TactileFrame((TactileState.HIGH,) * 20),
                speech=(SpeechRequest(
                    "Setting updated.",
                    message_id="settings.updated",
                    message_type=SpeechMessageType.MENU_OPTION,
                    lens_id="test",
                    blocks_tactile=True,
                ),),
            ))
            self.assertEqual(output.tactile, TactileFrame.off())
        finally:
            controller.close()

    def test_settings_menu_option_uses_reusable_audio_parts(self):
        registry = SettingsRegistry()
        registry.register_scope("test", (
            SettingSpec(
                "enabled", "Enabled", "bool", True,
                label_audio_key="settings.label.enabled",
            ),
        ))
        editor = SettingsEditor(SettingsTarget("test", "Test Settings", registry))

        output = editor.update(None, HandInputState())
        option = output.speech[-1]
        self.assertEqual(
            [part.clip_id for part in option.audio_parts],
            ["settings.label.enabled", "settings.current_value", "settings.value.on"],
        )

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
