# Becker Bearings screen UI

The developer screen runs with the compute layer in a background worker and a
single active lens. From the repository root:

```bat
begin.bat
```

Arguments may be passed through to the application. By default it replays the
configured stereo recording; use `begin.bat --camera` for the physical stereo
camera or `begin.bat --recording <name>` to choose a recording.

The initial active lens is `src/lenses/main-menu.py` when present; otherwise it
falls back to the development placeholder. The keyboard simulator maps arrow
keys or WASD to the joystick and Space/Enter to the button. The SVG
must contain exactly `point-00` through `point-19`, each with `cx` and `cy`
attributes. Pressing the button in the main-menu lens announces the selected
point through the audio service.
