# Becker Bearings

## What we are making

This project is software for a tactile hand interface intended to let a blind
person walk around and navigate without sight.

The physical interface has:

- 20 trinary or binary points of contact with the user's hand.
- One joystick with one axis.
- One button.

For the person using the system, this physical interface is the only interface
they will know. The screen interface is for development and/or someone who is
with the blind person.

The screen UI has a header, footer, and four equally sized cells in a 2×2 grid:

- Top-left: a live preview of exactly what the tactile grip is displaying.
- Top-right: lens-specific information. The lens controls this content.
- Bottom-left: the current disparity map from the most recently processed frame.
- Bottom-right: the lens-view panel. A lens may use the top-down 2D view and add
  its own overlay, or control how the panel looks.
- Header: the current text being read to the user.
- Footer: compute-layer statistics, not lens-specific statistics.

The grip SVG is [`src/assets/grip.svg`](src/assets/grip.svg). Its point IDs are
`point-00` through `point-19`.

## Layers

The project is organized into these layers:

1. Compute layer: always running under the hood and responsible for camera
   input and calculations.
2. Lens Controller: provides tools to lenses and handles switching lenses.
3. Lens layer: pure UI on top of the other layers. It reads the information it
   needs and handles joystick input.

There is exactly one active lens at a time. Each lens is modular, is represented
by a class, is instantiated when started, and has a destroy method when closed.
Each lens has a manifest containing its name, description, and settings options.
Lens-specific settings use the universal settings mechanism and include a reset
to default option.

Layers need to be able to play audio and read text to the user.

The examples discussed for lenses—Main Menu, Settings, Rays, and Person
Follow—are examples of possible lenses. They are not instructions to implement
those lenses unless specifically requested.

## Lens scripts

Lens scripts belong in [`src/lenses`](src/lenses). Python scripts in that folder
are automatically discovered and imported as lenses. Lens files may contain
hyphens in their filenames.

The current lens in [`src/lenses/main-menu.py`](src/lenses/main-menu.py) is a
simple tactile test lens. It starts with all points off and advances the active
point from `point-00` through `point-19` each time the button is pressed. It then
wraps back to `point-00`. It announces the selected point through the audio
service.

## Running the screen UI

From the repository root:

```bat
begin.bat
```

Arguments may be passed through to the application. The UI replays the
configured stereo recording by default. Use `begin.bat --camera` to use the
physical stereo camera or `begin.bat --recording <name>` to choose a recording.

For development control testing:

- Up/Down or W/S control the simulated joystick; Space or Enter simulates the button.
- Space or Enter simulates the button.

The grip preview reflects the tactile frame sent through the screen tactile
output. The current SVG preview preserves the grip's aspect ratio and contains
it within its cell.
