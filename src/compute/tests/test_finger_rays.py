import pathlib
import sys
import unittest
from types import SimpleNamespace

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from module.depth_mapper import DepthResult
from module.finger_rays import analyze_finger_sectors
from module.ground_plane import FloorEstimate


class FingerRayAnalysisTests(unittest.TestCase):
    def _frame(self):
        # A one-metre object in each of four angular sectors. The second row
        # sits above the floor plane; the first row is floor-like support.
        width, height, focal, baseline = 4, 2, 1.0, 1.0
        q = np.array([
            [1, 0, 0, -1.5],
            [0, 1, 0, 0],
            [0, 0, 0, focal],
            [0, 0, 1 / baseline, 0],
        ], np.float64)
        disparity = np.ones((height, width), np.float32)
        confidence = np.full((height, width), 2, np.uint8)
        gray = np.zeros((height, width), np.uint8)
        return DepthResult(disparity, confidence, gray, q, 16)

    def _floor(self):
        return FloorEstimate(
            normal_cam=np.array([0.0, -1.0, 0.0]),
            height_m=0.0,
            rotation_grav_cam=np.eye(3),
            fresh=True,
            usable=True,
            stale_s=0.0,
            inliers=10,
            candidates=10,
        )

    def _map(self, distance=None):
        return SimpleNamespace(
            settings={
                "min_range_m": 0.5,
                "max_range_m": 3.0,
                "floor_height_tol_m": 0.05,
                "obstacle_max_height_m": 2.0,
                "hole_min_below_m": 0.20,
            },
            tracking_ok=True,
            nearest_obstacle=lambda **_kwargs: distance,
        )

    def test_map_distance_is_split_into_four_equal_sectors(self):
        analysis = analyze_finger_sectors(
            self._frame(), self._map(1.0), 3.0)
        self.assertEqual(len(analysis.sectors), 4)
        self.assertTrue(all(sector.source == "map" for sector in analysis.sectors))
        self.assertTrue(all(sector.nearest_distance_m is not None
                            for sector in analysis.sectors))

    def test_floor_depth_does_not_trigger_a_sector(self):
        analysis = analyze_finger_sectors(
            self._frame(), self._map(), 3.0)
        self.assertTrue(all(sector.nearest_distance_m is None
                            for sector in analysis.sectors))

    def test_palm_mode_is_represented_by_five_slots(self):
        analysis = analyze_finger_sectors(
            self._frame(), self._map(), 3.0, slot_count=5)
        self.assertEqual(analysis.slot_count, 5)


if __name__ == "__main__":
    unittest.main()
