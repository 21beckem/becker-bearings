"""Manifest-driven settings storage."""


class SettingsRegistry:
    def __init__(self):
        self._values = {}

    def register(self, manifest):
        values = self._values.setdefault(manifest.lens_id, {})
        for spec in manifest.settings:
            values.setdefault(spec.key, spec.default)

    def get(self, lens_id, key):
        return self._values[lens_id][key]

    def set(self, lens_id, key, value):
        self._values[lens_id][key] = value

    def values(self, lens_id):
        return dict(self._values.get(lens_id, {}))

    def reset(self, manifest):
        self._values[manifest.lens_id] = {
            spec.key: spec.default for spec in manifest.settings
        }


class LensContext:
    def __init__(self, settings, audio):
        self.settings = settings
        self.audio = audio
