# Becker Bearings screen UI

The developer screen runs with the compute layer in a background worker and a
single active lens. From the repository root:

```bat
begin.bat
```

Arguments may be passed through to the application. By default it replays the
configured stereo recording; use `begin.bat --camera` for the physical stereo
camera or `begin.bat --recording <name>` to choose a recording.

The initial active lens is `src/lenses/main_menu.py`. The keyboard simulator
maps Up/Down or W/S to the single-axis joystick and Space/Enter to the button.
Left/Right and A/D are not controls. The SVG
must contain exactly `point-00` through `point-19`, each with `cx` and `cy`
attributes. Pressing the button in the main-menu lens announces the selected
point through the audio service.

## Tactile animations

Lenses can play a one-shot animation through their context. The animation is
rendered over the lens's current tactile frame and is sent to both the screen
preview and the physical grip:

```python
from interface.tactile_animation import RippleAnimation, WaveAnimation

self.context.play_tactile(RippleAnimation(origin="center-center"))
self.context.play_tactile(WaveAnimation(origin="bottom-right"))
```

Named origins use the nearest physical point from `grip.svg`, so they work
with the grip's irregular geometry. Starting another animation replaces the
current one; `context.controller.stop_tactile()` cancels it explicitly.

If `src/assets/audio/manifest.json` is present, the audio service preloads its
generated WAV clips through Qt Multimedia and plays exact phrase matches
immediately. Speech without a matching clip continues through the existing
runtime TTS backend.
