"""Iso-intensity boundary extraction followed by a metric enclosing rectangle."""

from dataclasses import dataclass
from numbers import Real

import cv2
import numpy as np

from .calibration import PlanarCalibration


@dataclass(frozen=True)
class RectangleMeasurement:
    """Unlabeled sides: length is the longer side; width is the shorter side."""

    length_mm: float
    width_mm: float
    corners_mm: tuple[tuple[float, float], ...]


def _boundary_crossings(image, mask, threshold):
    # Interpolate along grid edges between adjacent sample centers. For a
    # binary step at threshold 127.5, the crossing is halfway between centers.
    parts = []
    for axis in (0, 1):
        first = image[:-1, :] if axis == 0 else image[:, :-1]
        second = image[1:, :] if axis == 0 else image[:, 1:]
        changed = np.diff(mask, axis=axis) != 0
        y, x = np.nonzero(changed)
        fraction = (threshold - first[y, x]) / (second[y, x] - first[y, x])
        points = np.column_stack((x, y)).astype(np.float64)
        points[:, 1 - axis] += fraction
        parts.append(points)
    return np.concatenate(parts)


def _enclosing_rectangle(points_mm):
    # Center and scale before OpenCV's float32 operation to limit loss of
    # precision for metric coordinate systems with large offsets.
    origin = points_mm.mean(axis=0)
    local = points_mm - origin
    scale = np.max(np.abs(local))
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("Boundary has no measurable extent")
    rectangle = cv2.minAreaRect((local / scale).astype(np.float32))
    sides = sorted(float(side) * scale for side in rectangle[1])
    if sides[0] <= scale * 1e-7:
        raise ValueError("Boundary is degenerate")
    corners = cv2.boxPoints(rectangle).astype(np.float64) * scale + origin
    return RectangleMeasurement(
        length_mm=sides[1], width_mm=sides[0],
        corners_mm=tuple(tuple(float(value) for value in p) for p in corners),
    )


def measure_rectangle(image, calibration: PlanarCalibration, *, threshold=127.5):
    """Estimate the enclosing rectangle of one bright object on a dark field.

    image must be a 2D uint8 grayscale image, using the calibration's unchanged
    pixel geometry. Threshold is an intensity in [0, 255), never a dimension.
    Reject empty, fragmented, holed, undersampled or border-clipped foreground.
    This function does not certify rectangularity or classify conformity.
    """
    image = np.asarray(image)
    if image.ndim != 2 or min(image.shape, default=0) < 3 or image.dtype != np.uint8:
        raise ValueError("image must be a 2D uint8 array at least 3x3")
    if not isinstance(calibration, PlanarCalibration):
        raise ValueError("calibration must be a PlanarCalibration")
    if (not isinstance(threshold, Real) or isinstance(threshold, bool)
            or not np.isfinite(threshold) or not 0 <= threshold < 255):
        raise ValueError("threshold must be a finite intensity in [0, 255)")
    mask = (image > threshold).astype(np.uint8)
    if mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any():
        raise ValueError("Foreground touches the image border")
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
    if len(contours) != 1 or hierarchy is None:
        raise ValueError("Expected exactly one connected object without holes")
    if cv2.contourArea(contours[0]) < 4:
        raise ValueError("Foreground is too small for measurement")
    boundary_px = _boundary_crossings(image.astype(np.float64), mask, threshold)
    # A rectangle in pixel space is generally not a rectangle on the plane.
    # Transform the boundary itself, then fit in the metric coordinate system.
    return _enclosing_rectangle(calibration.transform(boundary_px))
