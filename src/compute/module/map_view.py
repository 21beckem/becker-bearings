"""Cheap top-down diagnostic rendering, separate from map integration."""

import math

import cv2
import numpy as np

from .image_tools import ImageTools
from .obstacle_map import ObstacleMap


def render_map(grid, pixels_per_cell=3, fov_deg=46.0):
    """Return a BGR top-down image; forward world Z points toward image top."""
    states = grid.state_grid()
    palette = np.array([[50, 50, 50], [65, 120, 55],
                        [40, 45, 230], [180, 40, 180],
                        [45, 95, 125]], np.uint8)
    image = np.flipud(palette[states])
    # A walked footprint is useful context, but it is still UNKNOWN unless
    # solid floor was measured. Hatch it in a distinct color rather than
    # turning it into a navigation-free cell.
    traversed_unknown = (states == ObstacleMap.UNKNOWN) & grid.walked_path_mask()
    rows, cols = np.indices(states.shape)
    remembered_hatch = (states == ObstacleMap.REMEMBERED) & ((rows + cols) % 2 == 0)
    image[np.flipud(remembered_hatch)] = (50, 50, 50)
    hatch = traversed_unknown & ((rows + cols) % 3 != 0)
    image[np.flipud(hatch)] = (115, 100, 35)
    image = cv2.resize(image, None, fx=pixels_per_cell, fy=pixels_per_cell,
                       interpolation=cv2.INTER_NEAREST)
    if grid.pose is not None:
        x = int(round((grid.pose.x_m - grid.origin_x_m) / grid.cell_m * pixels_per_cell))
        y = int(round((grid.side - (grid.pose.z_m - grid.origin_z_m) / grid.cell_m)
                      * pixels_per_cell))
        length = int(round(0.7 / grid.cell_m * pixels_per_cell))
        color = (255, 255, 255) if grid.tracking_ok else (0, 180, 255)
        cv2.circle(image, (x, y), max(3, pixels_per_cell), color, -1)
        for offset in (-fov_deg / 2, 0, fov_deg / 2):
            angle = grid.pose.yaw_rad + math.radians(offset)
            end = (int(round(x + length * math.sin(angle))),
                   int(round(y - length * math.cos(angle))))
            cv2.line(image, (x, y), end, color, 1, cv2.LINE_AA)
    cv2.putText(image, "green: floor  teal: walked  amber: remembered",
                (5, image.shape[0] - 8), cv2.FONT_HERSHEY_SIMPLEX,
                0.32 * pixels_per_cell / 3, (240, 240, 240), 1, cv2.LINE_AA)
    return image


def render_finger_rays(grid, analysis, pixels_per_cell=3):
    """Render the four Finger Rays sectors over the top-down map."""
    image = render_map(grid, pixels_per_cell=pixels_per_cell,
                       fov_deg=analysis.hfov_deg)
    if grid.pose is None:
        cv2.putText(image, "waiting for pose", (8, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 255), 1,
                    cv2.LINE_AA)
        return image

    def point_at(distance_m, angle_deg):
        angle = grid.pose.yaw_rad + math.radians(angle_deg)
        x = grid.pose.x_m + distance_m * math.sin(angle)
        z = grid.pose.z_m + distance_m * math.cos(angle)
        return (int(round((x - grid.origin_x_m) / grid.cell_m * pixels_per_cell)),
                int(round((grid.side - (z - grid.origin_z_m) / grid.cell_m)
                          * pixels_per_cell)))

    center = point_at(0.0, 0.0)
    overlay = image.copy()
    for sector in analysis.sectors:
        angles = np.linspace(sector.start_deg, sector.end_deg, 25)
        polygon = np.array([center] + [point_at(analysis.max_range_m, angle)
                                       for angle in angles], np.int32)
        if sector.nearest_distance_m is None:
            color = (75, 75, 75)
        elif sector.source == "current":
            color = (35, 135, 215)
        else:
            color = (145, 65, 180)
        cv2.fillPoly(overlay, [polygon], color)
    image = cv2.addWeighted(overlay, 0.28, image, 0.72, 0)

    # Sector boundaries make the display a set of pie slices, not four
    # centerline rays.
    for sector in analysis.sectors:
        for angle in (sector.start_deg,):
            cv2.line(image, center, point_at(analysis.max_range_m, angle),
                     (235, 235, 235), 1, cv2.LINE_AA)
    cv2.line(image, center, point_at(analysis.max_range_m,
                                     analysis.sectors[-1].end_deg),
             (235, 235, 235), 1, cv2.LINE_AA)

    # One tick arc per boundary between tactile distance levels. In the
    # default mode this produces two close/near/far boundaries; with palm
    # enabled it produces four boundaries for five levels.
    span = analysis.max_range_m - analysis.min_range_m
    for boundary in range(1, analysis.slot_count):
        distance = analysis.min_range_m + span * boundary / analysis.slot_count
        arc = np.array([
            point_at(distance, angle)
            for angle in np.linspace(analysis.sectors[0].start_deg,
                                     analysis.sectors[-1].end_deg, 80)
        ], np.int32)
        cv2.polylines(image, [arc], False, (250, 220, 90), 1, cv2.LINE_AA)
        for sector in analysis.sectors:
            angle = sector.center_deg
            inner = point_at(max(0.0, distance - 0.035), angle)
            outer = point_at(distance + 0.035, angle)
            cv2.line(image, inner, outer, (255, 255, 255), 2, cv2.LINE_AA)

    for sector in analysis.sectors:
        distance = sector.nearest_distance_m
        if distance is None:
            continue
        marker = point_at(distance, sector.center_deg)
        cv2.circle(image, marker, max(3, pixels_per_cell), (0, 255, 255), -1)
        cv2.putText(image, f"{distance:.1f}m", (marker[0] + 4, marker[1] - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1,
                    cv2.LINE_AA)

    status = "tracking" if analysis.tracking_ok else "tracking lost"
    cv2.putText(image, f"{analysis.slot_count} levels | {status}", (8, 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (240, 240, 240), 1,
                cv2.LINE_AA)
    return image


class MapWindow:
    """Companion OpenCV window; does not alter DepthWindow's API."""

    def __init__(self, name="Obstacle map | green: floor | amber: remembered"):
        self.name = name
        self.is_open = False

    def __enter__(self):
        cv2.namedWindow(self.name, cv2.WINDOW_NORMAL)
        self.is_open = True
        return self

    def update(self, result, grid):
        if not self.is_open:
            return
        depth_image = ImageTools.depth_image(result)
        fov_deg = math.degrees(2 * math.atan(result.gray.shape[1] / (2 * result.Q[2, 3])))
        map_image = render_map(grid, pixels_per_cell=2, fov_deg=fov_deg)
        map_image = cv2.resize(map_image, (depth_image.shape[0], depth_image.shape[0]),
                               interpolation=cv2.INTER_NEAREST)
        cv2.imshow(self.name, np.hstack((depth_image, map_image)))
        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord("q")):
            self.close()
            return
        try:
            visible = cv2.getWindowProperty(self.name, cv2.WND_PROP_VISIBLE)
        except cv2.error:
            visible = 0
        if visible < 1:
            self.close()

    def close(self):
        if self.is_open:
            self.is_open = False
            try:
                cv2.destroyWindow(self.name)
            except cv2.error:
                pass

    def __exit__(self, *_):
        self.close()
