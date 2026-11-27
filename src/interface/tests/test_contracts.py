import pathlib
import unittest

from interface.contracts import (
    HandInputState, LensOutput, TactileFrame, TactileState,
)
from interface.grip_svg import read_grip_points


ROOT = pathlib.Path(__file__).resolve().parents[2]


class ContractTests(unittest.TestCase):
    def test_tactile_frame_requires_twenty_points(self):
        with self.assertRaises(ValueError):
            TactileFrame((TactileState.OFF,) * 19)

    def test_tactile_frame_normalizes_integer_states(self):
        frame = TactileFrame((0, 1, 2) + (0,) * 17)
        self.assertEqual(frame.points[1], TactileState.LOW)
        self.assertEqual(frame.points[2], TactileState.HIGH)

    def test_grip_contains_all_points_in_numeric_order(self):
        points = read_grip_points(ROOT / "assets" / "grip.svg")
        self.assertEqual(len(points), 20)
        self.assertEqual(points[0], (78.682, 213.565))
        self.assertEqual(points[-1], (424.225, 512.792))

    def test_lens_output_defaults_to_safe_tactile_state(self):
        self.assertEqual(LensOutput().tactile, TactileFrame.off())

    def test_joystick_values_are_normalized(self):
        with self.assertRaises(ValueError):
            HandInputState(joystick=1.1)


if __name__ == "__main__":
    unittest.main()
