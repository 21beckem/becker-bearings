"""Lifecycle and output coordination for the active lens."""

import importlib.util
import inspect
from pathlib import Path
import re
from dataclasses import replace

from .audio import AudioService
from .contracts import Lens, LensOutput
from .settings import LensContext, SettingsRegistry
from .tactile import ScreenTactileOutput


class LensController:
    def __init__(self, tactile=None, audio=None, settings=None):
        self.tactile = tactile or ScreenTactileOutput()
        self.audio = audio or AudioService()
        self.settings = settings or SettingsRegistry()
        self._factories = {}
        self._active = None
        self._context = LensContext(self.settings, self.audio)
        self.last_output = LensOutput()
        self._previous_button_pressed = False

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
        self._active.start(self._context)

    def update(self, snapshot, input_state):
        if self._active is None:
            return self.last_output
        pressed = input_state.button_pressed and not self._previous_button_pressed
        self._previous_button_pressed = input_state.button_pressed
        normalized_input = replace(input_state, button_pressed=pressed)
        output = self._active.update(snapshot, normalized_input)
        if not isinstance(output, LensOutput):
            raise TypeError("A lens update must return LensOutput")
        self.tactile.send(output.tactile)
        for request in output.speech:
            self.audio.speak(request.text, request.interrupt, request.priority)
        self.last_output = output
        return output

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
