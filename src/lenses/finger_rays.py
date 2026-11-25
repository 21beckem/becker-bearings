"""Four-sector distance lens for the tactile grip."""

from compute.module.finger_rays import analyze_finger_sectors
from interface.contracts import (
    Lens, LensManifest, LensOutput, SettingSpec, TactileFrame, TactileState,
)


class FingerRaysLens(Lens):
    manifest = LensManifest(
        lens_id="finger_rays",
        name="Finger Rays",
        description=(
            "Splits the visible field into four equal sectors and encodes "
            "the nearest object distance on each finger."
        ),
        settings=(
            SettingSpec(
                key="reverse_distance_mapping",
                label="Reverse distance mapping",
                value_type="bool",
                default=False,
                description="Put close objects at the fingertip and far objects at the base.",
            ),
            SettingSpec(
                key="include_palm",
                label="Include palm",
                value_type="bool",
                default=False,
                description="Use the two palm points for five distance levels instead of three.",
            ),
            SettingSpec(
                key="ray_length_m",
                label="Field distance",
                value_type="float",
                default=3.0,
                description="Maximum distance represented by each sector.",
                minimum=0.5,
                maximum=3.0,
            ),
        ),
    )

    _FINGER_BASES = (0, 5, 10, 15)

    def __init__(self):
        self.context = None

    def start(self, context):
        self.context = context

    def update(self, snapshot, input_state):
        values = self.context.settings.values(self.manifest.lens_id)
        include_palm = bool(values.get("include_palm", False))
        reverse = bool(values.get("reverse_distance_mapping", False))
        slot_count = 5 if include_palm else 3
        ray_length_m = float(values.get("ray_length_m", 3.0))

        points = [TactileState.OFF] * 20
        if snapshot is None:
            return LensOutput(
                tactile=TactileFrame(tuple(points)),
                header_text="Finger Rays waiting for depth data",
                info_title=self.manifest.name,
                info_lines=("Waiting for a processed stereo frame.",),
                view_mode="finger_rays",
            )

        analysis = analyze_finger_sectors(
            snapshot.result,
            snapshot.obstacle_map,
            ray_length_m,
            slot_count=slot_count,
        )
        sector_lines = []
        detected = 0
        for sector in analysis.sectors:
            distance = sector.nearest_distance_m
            if distance is None:
                sector_lines.append(f"Sector {sector.index + 1}: no object detected")
                continue
            detected += 1
            slot = self._point_offset(distance, analysis, reverse)
            points[self._FINGER_BASES[sector.index] + slot] = TactileState.HIGH
            sector_lines.append(
                f"Sector {sector.index + 1}: {distance:.2f} m "
                f"({sector.source}, point {self._FINGER_BASES[sector.index] + slot:02d})"
            )

        direction = "reversed" if reverse else "tip=far / base=close"
        level_text = "5 distance levels including palm" if include_palm else "3 finger distance levels"
        header = f"Finger Rays: {detected}/4 sectors detected"
        return LensOutput(
            tactile=TactileFrame(tuple(points)),
            header_text=header,
            info_title=self.manifest.name,
            info_lines=(
                f"Four equal sectors across {analysis.hfov_deg:.1f}° of horizontal field of view.",
                f"Range: {analysis.min_range_m:.2f}–{analysis.max_range_m:.2f} m; {level_text}.",
                f"Mapping: {direction}.",
                *sector_lines,
            ),
            view_mode="finger_rays",
            view_payload=analysis,
        )

    @staticmethod
    def _point_offset(distance_m, analysis, reverse):
        span = analysis.max_range_m - analysis.min_range_m
        fraction = max(0.0, min(1.0, (distance_m - analysis.min_range_m) / span))
        band_from_close = min(analysis.slot_count - 1,
                              int(fraction * analysis.slot_count))
        if reverse:
            return band_from_close
        return analysis.slot_count - 1 - band_from_close

    def destroy(self):
        self.context = None
