"""Lifecycle and output coordination for the active lens."""

import importlib.util
import inspect
from pathlib import Path
import re
from dataclasses import replace
from time import monotonic

from .audio import AudioService
from .contracts import (
    Lens, LensOutput, SpeechCategory, SpeechMessageType, SpeechRequest,
)
from .settings import LensContext, SettingsRegistry, SYSTEM_SETTINGS
from .tactile import ScreenTactileOutput
from .menu import MenuItem, MenuNavigator
from .settings_editor import SettingsEditor, SettingsTarget
from .debug import debug


class LensController:
    def __init__(self, tactile=None, audio=None, settings=None):
        self.tactile = tactile or ScreenTactileOutput()
        self.audio = audio or AudioService()
        self.settings = settings or SettingsRegistry()
        self.settings.register_scope("system", SYSTEM_SETTINGS)
        self._factories = {}
        self._active = None
        self._context = LensContext(self.settings, self.audio, self)
        self.last_output = LensOutput()
        self._previous_button_pressed = False
        self._last_button_press_s = None
        self._quick_menu = None
        self._quick_menu_lens_id = None
        self._quick_menu_editor = None
        self._quick_menu_notice = ()
        self._pending_entry_speech = None

    @property
    def active_lens(self):
        return self._active

    def has_lens(self, lens_id):
        return lens_id in self._factories

    def register(self, lens_factory):
        manifest = lens_factory().manifest
        self._factories[manifest.lens_id] = lens_factory
        self.settings.register(manifest)

    def discover_directory(self, directory):
        """Import every Python lens script and register its Lens subclasses."""
        for lens_factory in discover_lenses(directory):
            self.register(lens_factory)

    def start(self, lens_id):
        if lens_id not in self._factories:
            raise KeyError(f"Unknown lens {lens_id!r}")
        if self._active is not None:
            self._active.destroy()
        self._active = self._factories[lens_id]()
        self.settings.register(self._active.manifest)
        # A lens switch may happen while the selecting button is still held.
        # Do not carry that physical state into the new lens or its shortcut.
        self._previous_button_pressed = False
        self._last_button_press_s = None
        self._pending_entry_speech = self._entry_speech(
            f"Entering {self._active.manifest.name}",
            f"lens.{lens_id}.entry",
            lens_id,
        )
        self._active.start(self._context)
        debug("lens_started lens_id=%s name=%s", lens_id, self._active.manifest.name)

    def update(self, snapshot, input_state):
        if self._active is None:
            return self.last_output
        pressed = input_state.button_pressed and not self._previous_button_pressed
        self._previous_button_pressed = input_state.button_pressed
        normalized_input = replace(input_state, button_pressed=pressed)
        if (pressed or input_state.joystick):
            debug(
                "controller_input lens=%s x=%s y=%s button_pressed=%s button_down=%s",
                self._active.manifest.lens_id,
                input_state.joystick,
                pressed, input_state.button_down,
            )

        if pressed:
            now = input_state.timestamp_s or monotonic()
            is_double = (
                self._last_button_press_s is not None and
                now - self._last_button_press_s <= 0.5
            )
            self._last_button_press_s = now
            if is_double and self._quick_menu is None:
                self._open_quick_menu()
                normalized_input = replace(normalized_input, button_pressed=False)

        if self._quick_menu_editor is not None:
            output = self._quick_menu_editor.update(snapshot, normalized_input)
            if self._quick_menu_editor is None:
                output = self._with_pending_entry(output)
                return self._deliver(output)
            output = self._with_pending_entry(output)
            return self._deliver(output)

        if self._quick_menu is not None:
            lens_before = self._active
            result = self._quick_menu.update(normalized_input)
            if result.selected is not None:
                self._select_quick_menu_item(result.selected.key)
                if self._active is not lens_before:
                    # Do not let the button press that selected a destination
                    # immediately select the destination's first menu item.
                    self._previous_button_pressed = normalized_input.button_down
            if self._quick_menu_notice:
                result = replace(result, speech=result.speech + self._quick_menu_notice)
                self._quick_menu_notice = ()
            if self._quick_menu is not None:
                output = self._quick_menu.output(result, header_text="Quick menu")
            else:
                output = self.last_output
            output = self._with_pending_entry(output)
            return self._deliver(output)

        lens_before = self._active
        output = self._active.update(snapshot, normalized_input)
        if self._active is not lens_before:
            # Lens switches can happen from inside a lens callback.  Consume
            # the currently held button as the switch action.
            self._previous_button_pressed = normalized_input.button_down
        if not isinstance(output, LensOutput):
            raise TypeError("A lens update must return LensOutput")
        output = self._with_pending_entry(output)
        return self._deliver(output)

    def _entry_speech(self, text, message_id, lens_id):
        return SpeechRequest(
            text,
            category=SpeechCategory.CONTEXT,
            message_id=message_id,
            message_type=SpeechMessageType.LENS_ENTRY,
            lens_id=lens_id,
        )

    def _with_pending_entry(self, output):
        if self._pending_entry_speech is None:
            return output
        has_entry = any(
            request.message_type == SpeechMessageType.LENS_ENTRY
            for request in output.speech
        )
        if not has_entry:
            output = replace(
                output,
                speech=(self._pending_entry_speech,) + output.speech,
            )
        self._pending_entry_speech = None
        return output

    def _deliver(self, output):
        self.tactile.send(output.tactile)
        for request in output.speech:
            instructions_enabled = self.settings.get("system", "menu_instructions")
            if (request.message_type == SpeechMessageType.INSTRUCTION and
                    not instructions_enabled):
                continue
            debug(
                "controller_speech text=%r type=%s id=%s instructions_enabled=%s",
                request.text, request.message_type, request.message_id,
                instructions_enabled,
            )
            self.audio.speak(
                request.text,
                category=request.category,
                clip_id=request.clip_id or request.message_id,
                message_id=request.message_id,
                message_type=request.message_type,
                lens_id=request.lens_id or self._active.manifest.lens_id,
                error_key=request.error_key,
                play_after_instructions=request.play_after_instructions,
            )
        self.last_output = output
        return output

    def _open_quick_menu(self):
        self._pending_entry_speech = self._entry_speech(
            "Entering Quick menu", "lens.quick_menu.entry", "quick_menu"
        )
        self._quick_menu_lens_id = self._active.manifest.lens_id
        self._quick_menu_editor = None
        self._quick_menu_notice = ()
        self._quick_menu = MenuNavigator(
            "Quick menu",
            (
                MenuItem("close", "Close menu", "Return to the current lens."),
                MenuItem("main_menu", "Main Menu", "Open the main menu."),
                MenuItem("lens_settings", "Lens settings", "Edit settings for the current lens."),
            ),
            instructions=(
                "Move the joystick to slide through quick menu options.",
                "Press the button to select.",
            ),
            instruction_id="quick_menu.instructions",
        )

    def _select_quick_menu_item(self, key):
        if key == "close":
            self._close_quick_menu()
        elif key == "main_menu":
            self._close_quick_menu()
            self.start("main_menu")
        elif key == "lens_settings":
            manifest = self._active.manifest
            if not manifest.settings:
                self._quick_menu_notice = (SpeechRequest(
                    "This lens has no settings.",
                    category=SpeechCategory.CONTENT,
                    message_id="quick_menu.no_settings",
                    message_type=SpeechMessageType.INSTRUCTION,
                ),)
                self._quick_menu = MenuNavigator(
                    "Quick menu",
                    (MenuItem("close", "Close menu"),),
                    instructions=("This lens has no settings.",),
                    instruction_id="quick_menu.no_settings.instructions",
                )
                return
            target = SettingsTarget(
                manifest.lens_id,
                f"{manifest.name} settings",
                self.settings,
                on_leave=self._close_quick_menu,
            )
            self._quick_menu = None
            self._quick_menu_editor = SettingsEditor(target)

    def _close_quick_menu(self):
        if self._active is not None:
            manifest = self._active.manifest
            self._pending_entry_speech = self._entry_speech(
                f"Resuming {manifest.name}",
                f"lens.{manifest.lens_id}.resume",
                manifest.lens_id,
            )
        self._quick_menu = None
        self._quick_menu_editor = None
        self._quick_menu_lens_id = None

    def close(self):
        if self._active is not None:
            self._active.destroy()
            self._active = None
        self.tactile.close()
        self.audio.close()


def discover_lenses(directory):
    """Yield Lens subclasses found in every ``*.py`` file in *directory*.

    Filenames may contain hyphens, which is why discovery uses file-based
    imports instead of normal Python package imports.
    """
    directory = Path(directory)
    if not directory.is_dir():
        return
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module_name = "user_lens_" + re.sub(r"\W+", "_", path.stem)
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for candidate in vars(module).values():
            if (inspect.isclass(candidate) and issubclass(candidate, Lens)
                    and candidate is not Lens and candidate.__module__ == module_name):
                yield candidate
