"""Validation and geometry loading for the tactile grip SVG."""

from pathlib import Path
import xml.etree.ElementTree as ElementTree


def read_grip_points(svg_path):
    """Return point coordinates in the required point-00..point-19 order."""
    root = ElementTree.parse(Path(svg_path)).getroot()
    points = {}
    for element in root.iter():
        point_id = element.attrib.get("id", "")
        if point_id.startswith("point-"):
            if "cx" not in element.attrib or "cy" not in element.attrib:
                raise ValueError(f"SVG point {point_id} must have cx and cy")
            points[point_id] = (float(element.attrib["cx"]), float(element.attrib["cy"]))
    expected = {f"point-{index:02d}" for index in range(20)}
    if set(points) != expected:
        missing = sorted(expected - set(points))
        extra = sorted(set(points) - expected)
        raise ValueError(f"SVG point IDs mismatch; missing={missing}, extra={extra}")
    return tuple(points[f"point-{index:02d}"] for index in range(20))
