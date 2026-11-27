import unittest

from interface.contracts import HandInputState, TactileState
from interface.tactile_animation import RippleAnimation, WaveAnimation
from lenses.animator import AnimatorLens


class FakeContext:
    def __init__(self):
        self.animations = []

    def play_tactile(self, animation):
        self.animations.append(animation)


class AnimatorLensTests(unittest.TestCase):
    def test_down_cycles_through_every_animation_option(self):
        context = FakeContext()
        lens = AnimatorLens()
        lens.start(context)

        labels = [lens.menu.current.label]
        for index in range(1, len(lens._OPTIONS)):
            lens.update(None, HandInputState(joystick=-1.0, timestamp_s=float(index)))
            lens.update(None, HandInputState(timestamp_s=float(index) + 0.01))
            labels.append(lens.menu.current.label)

        self.assertEqual(len(labels), len(lens._OPTIONS))
        self.assertEqual(len(set(labels)), len(labels))

    def test_button_plays_selected_animation(self):
        context = FakeContext()
        lens = AnimatorLens()
        lens.start(context)

        output = lens.update(
            None,
            HandInputState(button_pressed=True, timestamp_s=1.0),
        )

        self.assertEqual(len(context.animations), 1)
        self.assertIsInstance(context.animations[0], RippleAnimation)
        self.assertEqual(output.tactile.points[0], TactileState.HIGH)

        lens.update(None, HandInputState(joystick=1.0, timestamp_s=2.0))
        lens.update(None, HandInputState(timestamp_s=2.01))
        lens.update(None, HandInputState(button_pressed=True, timestamp_s=3.0))
        self.assertIsInstance(context.animations[1], WaveAnimation)


if __name__ == "__main__":
    unittest.main()
