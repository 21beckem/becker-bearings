"""Manifest-driven, transactional settings storage."""

import json
from pathlib import Path

from .contracts import SettingSpec


SYSTEM_SETTINGS = (
    SettingSpec(
        key="menu_instructions",
        label="Menu instructions",
        value_type="bool",
        default=True,
        description="Provides spoken navigation instructions when entering menus.",
        label_audio_key="settings.label.menu_instructions",
    ),
)


class SettingsRegistry:
    def __init__(self, storage_path=None):
        self._values = {}
        self._specs = {}
        self.storage_path = Path(storage_path) if storage_path else None
        self._load()

    def _load(self):
        if self.storage_path is None or not self.storage_path.exists():
            return
        try:
            self._values.update(json.loads(self.storage_path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            # A corrupt preference file must not prevent the device from starting.
            self._values = {}

    def register(self, manifest):
        self.register_scope(manifest.lens_id, manifest.settings)

    def register_scope(self, scope_id, specs):
        specs = tuple(specs)
        self._specs[scope_id] = specs
        values = self._values.setdefault(scope_id, {})
        for spec in specs:
            values.setdefault(spec.key, spec.default)

    def get(self, scope_id, key):
        return self._values[scope_id][key]

    def set(self, scope_id, key, value):
        self._values[scope_id][key] = value

    def values(self, scope_id):
        return dict(self._values.get(scope_id, {}))

    def specs(self, scope_id):
        return tuple(self._specs.get(scope_id, ()))

    def reset(self, manifest):
        self.reset_scope(manifest.lens_id)

    def reset_scope(self, scope_id):
        self._values[scope_id] = {
            spec.key: spec.default for spec in self.specs(scope_id)
        }

    def commit_defaults(self, scope_id):
        """Reset one scope and persist the reset immediately."""
        self.reset_scope(scope_id)
        self.save()

    def commit(self, scope_id, values):
        allowed = {spec.key for spec in self.specs(scope_id)}
        self._values[scope_id] = {
            key: value for key, value in values.items() if key in allowed
        }
        for spec in self.specs(scope_id):
            self._values[scope_id].setdefault(spec.key, spec.default)
        self.save()

    def save(self):
        if self.storage_path is None:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(
            json.dumps(self._values, indent=2, sort_keys=True), encoding="utf-8"
        )

    def transaction(self, scope_id):
        return SettingsTransaction(self, scope_id)


class SettingsTransaction:
    def __init__(self, registry, scope_id):
        self.registry = registry
        self.scope_id = scope_id
        self._draft = registry.values(scope_id)

    def get(self, key):
        return self._draft[key]

    def set(self, key, value):
        self._draft[key] = value

    def values(self):
        return dict(self._draft)

    def changed(self):
        return {
            key: (self.registry.values(self.scope_id).get(key), value)
            for key, value in self._draft.items()
            if self.registry.values(self.scope_id).get(key) != value
        }

    def reset(self):
        self._draft = {
            spec.key: spec.default for spec in self.registry.specs(self.scope_id)
        }

    def commit(self):
        self.registry.commit(self.scope_id, self._draft)


class LensContext:
    def __init__(self, settings, audio, controller=None):
        self.settings = settings
        self.audio = audio
        self.controller = controller

    def play_tactile(self, animation):
        """Start a tactile animation on the shared screen/hardware output."""
        if self.controller is None:
            raise RuntimeError("tactile animations require a lens controller")
        self.controller.play_tactile(animation)
