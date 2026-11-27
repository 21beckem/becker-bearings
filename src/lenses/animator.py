"""Tactile animation test lens."""

from dataclasses import dataclass

from interface.contracts import Lens, LensManifest
from interface.menu import MenuItem, MenuNavigator
from interface.tactile_animation import RippleAnimation, WaveAnimation


@dataclass(frozen=True)
class AnimationOption:
    key: str
    label: str
    description: str
    factory: object


class AnimatorLens(Lens):
    manifest = LensManifest(
        lens_id="animator",
        name="Animator",
        description="Test tactile animations on the grip.",
    )

    _OPTIONS = (
        AnimationOption(
            "animator.ripple_center",
            "Ripple from center",
            "An expanding ripple starting at the center of the grip.",
            lambda: RippleAnimation(origin="center-center"),
        ),
        AnimationOption(
            "animator.wave_bottom_right",
            "Wave from bottom right",
            "A diagonal wave moving inward from the bottom right.",
            lambda: WaveAnimation(origin="bottom-right"),
        ),
        AnimationOption(
            "animator.ripple_top_left",
            "Ripple from top left",
            "An expanding ripple starting at the top left of the grip.",
            lambda: RippleAnimation(origin="top-left"),
        ),
        AnimationOption(
            "animator.ripple_top_right",
            "Ripple from top right",
            "An expanding ripple starting at the top right of the grip.",
            lambda: RippleAnimation(origin="top-right"),
        ),
        AnimationOption(
            "animator.ripple_bottom_left",
            "Ripple from bottom left",
            "An expanding ripple starting at the bottom left of the grip.",
            lambda: RippleAnimation(origin="bottom-left"),
        ),
    )

    def __init__(self):
        self.context = None
        self.menu = None

    def start(self, context):
        self.context = context
        self.menu = MenuNavigator(
            self.manifest.name,
            tuple(
                MenuItem(
                    option.key,
                    option.label,
                    option.description,
                    select=lambda option=option: self._play(option),
                )
                for option in self._OPTIONS
            ),
            instructions=(
                "Move the joystick to choose an animation.",
                "Press the button to play it.",
            ),
            instruction_id="animator.instructions",
        )

    def _play(self, option):
        self.context.play_tactile(option.factory())

    def update(self, snapshot, input_state):
        result = self.menu.update(input_state)
        if result.selected is not None and result.selected.select:
            result.selected.select()
        option = self._OPTIONS[self.menu.index]
        return self.menu.output(
            result,
            header_text=f"Animator: {option.label}",
            extra_info=(
                "Move the joystick to cycle through animations.",
                "Press the button to play the selected animation over the grip.",
            ),
        )

    def destroy(self):
        self.context = None
        self.menu = None
