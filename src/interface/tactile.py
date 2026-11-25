"""Tactile output and hand-input adapters."""

from dataclasses import dataclass
from threading import Event, Lock, Thread
from time import monotonic

from .contracts import HandInputState, TactileFrame, TactileState


class TactileOutput:
    def send(self, frame: TactileFrame):
        raise NotImplementedError

    def close(self):
        """Release resources owned by the output adapter, if any."""


class ChannelTactileOutput(TactileOutput):
    """Periodically transmit tactile frames to a channel-sender grip.

    ``send`` only replaces the frame to be transmitted.  A dedicated worker
    owns the serial sender and transmits the current frame on every clock tick,
    including ticks where the frame has not changed.

    ``sender`` is injectable so this adapter can be tested without hardware.
    When it is omitted, *port* is passed to :class:`ChannelSender`.
    """

    def __init__(self, port=None, baudrate=115200, interval_s=0.1, sender=None):
        if interval_s <= 0:
            raise ValueError("interval_s must be greater than zero")
        if sender is None and port is None:
            raise ValueError("port is required when sender is not provided")

        if sender is None:
            # Keep serial hardware optional for the screen-only development UI.
            from .channel_sender import ChannelSender
            sender = ChannelSender(port, baudrate)
        self._sender = sender
        self._interval_s = float(interval_s)
        self._frame = TactileFrame.off()
        self._lock = Lock()
        self._stop = Event()
        self._closed = False
        self._thread = Thread(target=self._run, name="tactile-output", daemon=True)
        self._thread.start()

    def send(self, frame: TactileFrame):
        if not isinstance(frame, TactileFrame):
            raise TypeError("frame must be a TactileFrame")
        with self._lock:
            if self._closed:
                raise RuntimeError("tactile output is closed")
            self._frame = frame

    def _run(self):
        next_tick = monotonic() + self._interval_s
        while not self._stop.is_set():
            wait_s = max(0.0, next_tick - monotonic())
            if self._stop.wait(wait_s):
                break

            with self._lock:
                frame = self._frame
            self._sender.set_all(tuple(point.value for point in frame.points))
            self._sender.send()

            next_tick += self._interval_s
            # Do not spin trying to catch up if serial I/O took longer than a
            # period.  The next transmission is still scheduled from the
            # internal clock rather than from completion of the previous send.
            if next_tick <= monotonic():
                next_tick = monotonic() + self._interval_s

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._stop.set()
        self._thread.join()
        self._sender.close()


class MirroredTactileOutput(TactileOutput):
    """Send each tactile frame to multiple output adapters."""

    def __init__(self, *outputs):
        if not outputs:
            raise ValueError("at least one tactile output is required")
        self._outputs = tuple(outputs)

    def send(self, frame: TactileFrame):
        for output in self._outputs:
            output.send(frame)

    def close(self):
        for output in self._outputs:
            output.close()


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
