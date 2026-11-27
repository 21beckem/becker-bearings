"""Time-based animations for the twenty-point tactile grip.

Animations operate on the SVG point geometry rather than assuming that the
points form a regular grid.  They return ordinary :class:`TactileFrame`
objects, so the screen preview and every hardware adapter see the same result.
"""

from math import hypot
from pathlib import Path
from time import monotonic

from .contracts import TactileFrame, TactileState
from .grip_svg import read_grip_points


_POINTS = None


def grip_points():
    """Return the grip point coordinates in point-00..point-19 order."""
    global _POINTS
    if _POINTS is None:
        svg_path = Path(__file__).resolve().parents[1] / "assets" / "grip.svg"
        _POINTS = read_grip_points(svg_path)
    return _POINTS


def _anchor(name, points):
    if not isinstance(name, str):
        return tuple(name)
    if name not in {"center-center", "top-left", "top-right",
                    "bottom-left", "bottom-right"}:
        raise ValueError(f"unknown tactile animation origin: {name!r}")
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x = min(xs) if "left" in name else max(xs) if "right" in name else (min(xs) + max(xs)) / 2
    y = min(ys) if "top" in name else max(ys) if "bottom" in name else (min(ys) + max(ys)) / 2
    # Named locations describe tactile points, not arbitrary locations outside
    # the grip.  Snap the ideal bounding-box anchor to the nearest real point,
    # using normalized axes so a corner means corner-like in the grip shape.
    x_span = max(xs) - min(xs)
    y_span = max(ys) - min(ys)
    target = ((x - min(xs)) / x_span, (y - min(ys)) / y_span)
    return min(
        points,
        key=lambda point: hypot(
            (point[0] - min(xs)) / x_span - target[0],
            (point[1] - min(ys)) / y_span - target[1],
        ),
    )


class TactileAnimation:
    """Base class for a one-shot tactile animation."""

    def __init__(self, duration_s, state=TactileState.HIGH, started_at=None):
        if duration_s <= 0:
            raise ValueError("duration_s must be greater than zero")
        self.duration_s = float(duration_s)
        self.state = TactileState(state)
        self.started_at = monotonic() if started_at is None else float(started_at)

    def frame_at(self, time_s, base_frame):
        """Render the animation at *time_s* over *base_frame*."""
        elapsed = max(0.0, float(time_s) - self.started_at)
        if elapsed >= self.duration_s:
            return base_frame
        active = self._active_points(elapsed)
        points = list(base_frame.points)
        for index in active:
            points[index] = self.state
        return TactileFrame(tuple(points))

    def finished(self, time_s):
        return float(time_s) - self.started_at >= self.duration_s

    def _active_points(self, elapsed_s):
        raise NotImplementedError


class RippleAnimation(TactileAnimation):
    """A ring expanding from an SVG-space origin."""

    def __init__(self, origin="center-center", duration_s=0.8,
                 width=45.0, state=TactileState.HIGH, started_at=None):
        if width <= 0:
            raise ValueError("width must be greater than zero")
        super().__init__(duration_s, state, started_at)
        points = grip_points()
        self.origin = _anchor(origin, points)
        self.width = float(width)
        self._distances = tuple(
            hypot(point[0] - self.origin[0], point[1] - self.origin[1])
            for point in points
        )
        self._max_distance = max(self._distances)

    def _active_points(self, elapsed_s):
        radius = self._max_distance * min(1.0, elapsed_s / self.duration_s)
        half_width = self.width / 2.0
        return tuple(index for index, distance in enumerate(self._distances)
                     if abs(distance - radius) <= half_width)


class WaveAnimation(TactileAnimation):
    """A diagonal wave moving inward from a named edge or corner.

    The wavefront travels from ``origin`` toward the grip center.  The
    ``width`` is measured in SVG coordinate units.
    """

    def __init__(self, origin="bottom-right", duration_s=0.8,
                 width=55.0, state=TactileState.HIGH, started_at=None):
        if width <= 0:
            raise ValueError("width must be greater than zero")
        super().__init__(duration_s, state, started_at)
        points = grip_points()
        self.origin = _anchor(origin, points)
        center = _anchor("center-center", points)
        direction = (center[0] - self.origin[0], center[1] - self.origin[1])
        length = hypot(*direction)
        self._distances = tuple(
            max(0.0, ((point[0] - self.origin[0]) * direction[0] +
                      (point[1] - self.origin[1]) * direction[1]) / length)
            for point in points
        )
        self.width = float(width)
        self._max_distance = max(self._distances)

    def _active_points(self, elapsed_s):
        distance = self._max_distance * min(1.0, elapsed_s / self.duration_s)
        half_width = self.width / 2.0
        return tuple(index for index, point_distance in enumerate(self._distances)
                     if abs(point_distance - distance) <= half_width)
