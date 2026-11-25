# Becker Bearings screen UI

The developer screen runs with the compute layer in a background worker and a
single active lens. From the repository root:

```powershell
$env:PYTHONPATH = "src"
\.venv\Scripts\python.exe -m interface.run
```

By default it replays the configured stereo recording. Use `--camera` for the
physical stereo camera or `--svg path/to/grip.svg` to override the tactile grip
asset.

The initial active lens is `src/lenses/main-menu.py` when present; otherwise it
falls back to the development placeholder. The keyboard simulator maps arrow
keys or WASD to the joystick and Space/Enter to the button. The SVG
must contain exactly `point-00` through `point-19`, each with `cx` and `cy`
attributes.
