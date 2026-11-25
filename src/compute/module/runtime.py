"""Compute-layer runtime and immutable handoff snapshots for the UI."""

from dataclasses import dataclass

from .benchmark import Benchmark
from .depth_mapper import DepthMapper
from .ground_plane import FloorEstimate, GroundPlaneEstimator
from .obstacle_map import ObstacleMap
from .pose_tracker import PoseTracker


@dataclass(frozen=True)
class ComputeSnapshot:
    """The latest compute result made available to a lens.

    The contained NumPy arrays and map are owned by the compute runtime. Lenses
    should treat them as read-only and use the public map query methods.
    """

    timestamp_s: float
    result: object
    floor: FloorEstimate
    pose: object
    obstacle_map: ObstacleMap
    benchmark: dict


class ComputeRuntime:
    """Own the always-on compute pipeline, without owning any display."""

    def __init__(self, config):
        self.config = config
        self.depth = DepthMapper(config)
        self.ground = GroundPlaneEstimator(config)
        self.tracker = PoseTracker(config)
        self.grid = ObstacleMap(config)
        self.benchmark = Benchmark().setup("capture", "depth", "mapping")

    def process(self, left, right, timestamp_s):
        with self.benchmark.measure("depth"):
            result = self.depth.compute(left, right)
        with self.benchmark.measure("mapping"):
            floor = self.ground.fit(result, timestamp_s)
            pose = self.tracker.update(result, floor, timestamp_s)
            if self.tracker.reset_map or self.tracker.loop_closure:
                self.grid.reset_local(self.tracker.map_epoch)
            self.grid.integrate(result, floor, pose, timestamp_s)
        return ComputeSnapshot(
            timestamp_s=timestamp_s,
            result=result,
            floor=floor,
            pose=pose,
            obstacle_map=self.grid,
            benchmark=self.benchmark.results(),
        )

    def finish(self):
        """Print and optionally save compute statistics at shutdown."""
        self.benchmark.display()
        output = self.config.get("benchmark", {}).get("output")
        if output is not None:
            self.benchmark.save(output)
