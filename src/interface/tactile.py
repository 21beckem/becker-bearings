"""Tactile output and hand-input adapters."""

from dataclasses import dataclass

from .contracts import HandInputState, TactileFrame, TactileState


class TactileOutput:
    def send(self, frame: TactileFrame):
        raise NotImplementedError


class ScreenTactileOutput(TactileOutput):
    """Development adapter that records the last commanded frame."""

    def __init__(self):
        self.last_frame = TactileFrame.off()

    def send(self, frame):
        self.last_frame = frame


class BinaryTactileOutput(TactileOutput):
    """Adapter wrapper for future binary hardware.

    LOW and HIGH both become active. The wrapped callback receives twenty bools.
    """

    def __init__(self, send_binary):
        self._send_binary = send_binary

    def send(self, frame):
        self._send_binary(tuple(point != TactileState.OFF for point in frame.points))


class HandInput:
    def read(self):
        raise NotImplementedError


class NullHandInput(HandInput):
    def read(self):
        return HandInputState()


@dataclass
class KeyboardHandInput(HandInput):
    """Keyboard simulator; UI code calls set_state from key handlers."""

    state: HandInputState = HandInputState()

    def read(self):
        return self.state

    def set_state(self, **changes):
        values = {
            "joystick_x": self.state.joystick_x,
            "joystick_y": self.state.joystick_y,
            "button_down": self.state.button_down,
            "button_pressed": self.state.button_pressed,
        }
        values.update(changes)
        self.state = HandInputState(**values)
