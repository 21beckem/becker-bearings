import time
import unittest

from interface.contracts import TactileFrame, TactileState
from interface.tactile import ChannelTactileOutput, CombinedHandInput, ScreenTactileOutput


class FakeChannelSender:
    def __init__(self):
        self.values = []
        self.closed = False

    def set_all(self, values):
        self.values.append(tuple(values))

    def send(self):
        pass

    def close(self):
        self.closed = True


class ChannelTactileOutputTests(unittest.TestCase):
    def test_sends_unchanged_frame_on_every_tick(self):
        sender = FakeChannelSender()
        output = ChannelTactileOutput(sender=sender, interval_s=0.01)
        try:
            frame = TactileFrame((TactileState.HIGH,) + (TactileState.OFF,) * 19)
            output.send(frame)
            deadline = time.monotonic() + 0.2
            while len(sender.values) < 3 and time.monotonic() < deadline:
                time.sleep(0.005)
        finally:
            output.close()

        self.assertGreaterEqual(len(sender.values), 3)
        self.assertTrue(all(values == (2,) + (0,) * 19 for values in sender.values))
        self.assertTrue(sender.closed)

    def test_combined_input_can_read_keyboard_without_serial_output(self):
        # The screen-only path must remain keyboard-only and never require a
        # serial sender to exist.
        output = ChannelTactileOutput(sender=FakeChannelSender(), interval_s=0.01)
        try:
            input_adapter = CombinedHandInput(output)
            input_adapter.set_state(joystick=1.0)
            self.assertEqual(input_adapter.read().joystick, 1.0)
        finally:
            output.close()


if __name__ == "__main__":
    unittest.main()
