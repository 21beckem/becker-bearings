"""Simple tactile point test lens."""

from interface.contracts import Lens, LensManifest, LensOutput, TactileFrame, TactileState


class MainMenuLens(Lens):
    manifest = LensManifest(
        lens_id="main-menu",
        name="Main Menu",
        description="Cycles through the twenty tactile grip points.",
    )

    def __init__(self):
        self.point_index = None

    def start(self, context):
        self.point_index = None

    def update(self, snapshot, input_state):
        if input_state.button_pressed:
            self.point_index = 0 if self.point_index is None else (self.point_index + 1) % 20

        points = [TactileState.OFF] * 20
        if self.point_index is not None:
            points[self.point_index] = TactileState.HIGH
            point_text = f"Point {self.point_index:02d} of 20"
        else:
            point_text = "No point selected"
        return LensOutput(
            tactile=TactileFrame(tuple(points)),
            header_text=point_text,
            info_title=self.manifest.name,
            info_lines=(
                "Press Space, Enter, or the button to advance.",
                point_text,
                "The highlighted point is the current tactile output.",
            ),
        )
