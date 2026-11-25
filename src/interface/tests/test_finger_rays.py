import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from compute.module.depth_mapper import DepthResult
from compute.module.finger_rays import FingerRayAnalysis, FingerRaySector
from compute.module.ground_plane import FloorEstimate
from interface.settings import LensContext, SettingsRegistry
from lenses.finger_rays import FingerRaysLens


class FingerRaysLensTests(unittest.TestCase):
    def _snapshot(self):
        q = np.array([
            [1, 0, 0, -1.5], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0],
        ], np.float64)
        result = DepthResult(
            np.ones((2, 4), np.float32),
            np.full((2, 4), 2, np.uint8),
            np.zeros((2, 4), np.uint8), q, 16)
        floor = FloorEstimate(
            np.array([0.0, -1.0, 0.0]), 0.0, np.eye(3), True, True,
            0.0, 10, 10)
        obstacle_map = SimpleNamespace(
            settings={
                "min_range_m": 0.5, "max_range_m": 3.0,
                "floor_height_tol_m": 0.05,
                "obstacle_max_height_m": 2.0,
                "hole_min_below_m": 0.20,
            },
            tracking_ok=True,
            nearest_obstacle=lambda **_kwargs: None,
        )
        return SimpleNamespace(result=result, floor=floor,
                               obstacle_map=obstacle_map)

    @staticmethod
    def _analysis(slot_count=3):
        sectors = tuple(
            FingerRaySector(index, -40.0 + index * 20.0,
                            -20.0 + index * 20.0, 1.0, "current")
            for index in range(4)
        )
        return FingerRayAnalysis(80.0, 3.0, 0.5, slot_count, sectors, 4, True)

    def _lens(self, **changes):
        settings = SettingsRegistry()
        settings.register(FingerRaysLens.manifest)
        for key, value in changes.items():
            settings.set("finger_rays", key, value)
        lens = FingerRaysLens()
        lens.start(LensContext(settings, None))
        return lens

    def test_default_uses_three_finger_points(self):
        with patch("lenses.finger_rays.analyze_finger_sectors",
                   return_value=self._analysis()):
            output = self._lens().update(self._snapshot(), None)
        active = [index for index, point in enumerate(output.tactile.points)
                  if point.value]
        self.assertEqual(active, [2, 7, 12, 17])

    def test_include_palm_uses_five_points(self):
        with patch("lenses.finger_rays.analyze_finger_sectors",
                   return_value=self._analysis(5)):
            output = self._lens(include_palm=True).update(self._snapshot(), None)
        active = [index for index, point in enumerate(output.tactile.points)
                  if point.value]
        self.assertEqual(active, [3, 8, 13, 18])

    def test_reversed_mapping_puts_close_objects_at_the_tip(self):
        with patch("lenses.finger_rays.analyze_finger_sectors",
                   return_value=self._analysis()):
            output = self._lens(reverse_distance_mapping=True).update(
                self._snapshot(), None)
        active = [index for index, point in enumerate(output.tactile.points)
                  if point.value]
        self.assertEqual(active, [0, 5, 10, 15])


if __name__ == "__main__":
    unittest.main()
