"""Current-frame horizontal field-of-view sectors for tactile lenses."""

from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class FingerRaySector:
    """One equal-angle sector and its nearest usable object distance."""

    index: int
    start_deg: float
    end_deg: float
    nearest_distance_m: float | None
    source: str = "none"

    @property
    def center_deg(self):
        return (self.start_deg + self.end_deg) / 2.0


@dataclass(frozen=True)
class FingerRayAnalysis:
    """Frame data needed by the Finger Rays lens and its screen overlay."""

    hfov_deg: float
    max_range_m: float
    min_range_m: float
    slot_count: int
    sectors: tuple[FingerRaySector, ...]
    object_samples: int
    tracking_ok: bool


def _horizontal_fov_deg(result):
    focal = float(result.Q[2, 3])
    if focal <= 0:
        raise ValueError("DepthResult.Q must contain a positive horizontal focal length")
    return math.degrees(2.0 * math.atan(result.gray.shape[1] / (2.0 * focal)))


def analyze_finger_sectors(result, obstacle_map, max_range_m,
                           slot_count=3, sector_count=4):
    """Summarize the nearest object in each equal horizontal FOV sector.

    Distance data comes exclusively from the integrated 2D obstacle map. The
    raw depth result is used only to calculate the calibrated horizontal FOV;
    this prevents looking at the floor from becoming a false obstacle.
    """
    if sector_count < 1:
        raise ValueError("sector_count must be positive")
    if slot_count not in (3, 5):
        raise ValueError("slot_count must be 3 or 5")

    settings = obstacle_map.settings
    min_range_m = float(settings["min_range_m"])
    max_supported_m = float(settings["max_range_m"])
    max_range_m = min(float(max_range_m), max_supported_m)
    if max_range_m <= min_range_m:
        raise ValueError("max_range_m must be greater than the compute minimum range")

    hfov_deg = _horizontal_fov_deg(result)
    sector_width = hfov_deg / sector_count
    starts = -hfov_deg / 2.0 + np.arange(sector_count) * sector_width
    ends = starts + sector_width

    nearest = [None] * sector_count
    sources = ["none"] * sector_count

    # The map is the sole source of distance data. In particular, do not
    # inspect current-frame points here: the floor is expected to be visible
    # when the person looks down and is not an obstacle for this lens.
    for index, (start, end) in enumerate(zip(starts, ends)):
        if obstacle_map is None:
            continue
        distance = obstacle_map.nearest_obstacle(
            direction_deg=float((start + end) / 2.0),
            width_deg=float(end - start))
        if distance is not None and min_range_m <= distance <= max_range_m:
            nearest[index] = float(distance)
            sources[index] = "map"

    sectors = tuple(
        FingerRaySector(index, float(start), float(end), nearest[index], sources[index])
        for index, (start, end) in enumerate(zip(starts, ends))
    )
    return FingerRayAnalysis(
        hfov_deg=float(hfov_deg),
        max_range_m=max_range_m,
        min_range_m=min_range_m,
        slot_count=slot_count,
        sectors=sectors,
        object_samples=0,
        tracking_ok=bool(getattr(obstacle_map, "tracking_ok", False)),
    )
