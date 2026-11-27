import unittest

from interface.contracts import TactileFrame, TactileState
from interface.tactile_animation import RippleAnimation, WaveAnimation, grip_points


class TactileAnimationTests(unittest.TestCase):
    def test_ripple_uses_grip_geometry_and_finishes_on_base_frame(self):
        animation = RippleAnimation(duration_s=1.0, width=30.0, started_at=0.0)
        base = TactileFrame((TactileState.LOW,) * 20)

        first = animation.frame_at(0.0, base)
        middle = animation.frame_at(0.5, base)
        self.assertTrue(any(state == TactileState.HIGH for state in first.points))
        self.assertTrue(any(state == TactileState.HIGH for state in middle.points))
        self.assertEqual(animation.frame_at(1.0, base), base)
        self.assertEqual(len(grip_points()), 20)

    def test_named_wave_reaches_bottom_right_first(self):
        animation = WaveAnimation(origin="bottom-right", duration_s=1.0,
                                  width=20.0, started_at=0.0)
        base = TactileFrame.off()
        frame = animation.frame_at(0.0, base)
        self.assertEqual(frame.points[19], TactileState.HIGH)

    def test_animation_preserves_unanimated_base_points(self):
        animation = RippleAnimation(duration_s=1.0, width=1.0, started_at=0.0)
        base = TactileFrame((TactileState.LOW,) * 20)
        frame = animation.frame_at(0.0, base)
        self.assertTrue(all(state in (TactileState.LOW, TactileState.HIGH)
                            for state in frame.points))


if __name__ == "__main__":
    unittest.main()
