"""Development-only lens used to exercise the first screen vertical slice."""

from .contracts import Lens, LensManifest, LensOutput


class DevelopmentLens(Lens):
    manifest = LensManifest(
        lens_id="development",
        name="Development",
        description="Shows compute health while the physical interface is being developed.",
    )

    def update(self, snapshot, input_state):
        tracking = "tracking" if snapshot.obstacle_map.tracking_ok else "tracking lost"
        floor = "floor ready" if snapshot.floor.usable else "floor unavailable"
        lines = (
            "The active lens is the development placeholder.",
            f"{tracking}; {floor}",
            f"integrated frames: {snapshot.obstacle_map.integrated_frames}",
            "Joystick and button simulator are ready.",
        )
        return LensOutput(
            header_text="Development lens",
            info_title=self.manifest.name,
            info_lines=lines,
        )
