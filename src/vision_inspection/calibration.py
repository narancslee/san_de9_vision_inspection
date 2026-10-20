"""Pixel-center to metric-plane homographies; lens distortion is out of scope."""

from dataclasses import dataclass

import cv2
import numpy as np


def _points(value, name, minimum=1):
    points = np.asarray(value, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) < minimum:
        raise ValueError(f"{name} must have shape (N, 2), N >= {minimum}")
    if not np.isfinite(points).all():
        raise ValueError(f"{name} must contain finite coordinates")
    return points


def _normalize(points):
    centered = points - points.mean(axis=0)
    scale = np.sqrt(np.mean(np.sum(centered**2, axis=1)))
    if scale == 0 or not np.isfinite(scale):
        raise ValueError("Calibration points must span a plane")
    return centered / scale


@dataclass(frozen=True, eq=False)
class PlanarCalibration:
    """A nonsingular 3x3 homography mapping (x_px, y_px) to (X_mm, Y_mm)."""

    pixel_to_plane: np.ndarray

    def __post_init__(self):
        matrix = np.array(self.pixel_to_plane, dtype=np.float64, copy=True)
        if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
            raise ValueError("pixel_to_plane must be a finite 3x3 matrix")
        norm = np.max(np.abs(matrix))
        if norm == 0:
            raise ValueError("pixel_to_plane must be nonsingular")
        matrix /= norm
        if np.linalg.matrix_rank(matrix) != 3:
            raise ValueError("pixel_to_plane must be nonsingular and well conditioned")
        # Immutable backing storage also prevents setflags(write=True).
        matrix = np.frombuffer(matrix.tobytes(), dtype=np.float64).reshape(3, 3)
        object.__setattr__(self, "pixel_to_plane", matrix)

    @classmethod
    def from_correspondences(cls, pixels, plane_mm):
        """Fit all paired control points, without RANSAC or outlier rejection.

        At least four correspondences in projectively general position are
        required. Callers must assess residuals and independent check points.
        """
        pixels = _points(pixels, "pixels", 4)
        plane_mm = _points(plane_mm, "plane_mm", 4)
        if pixels.shape != plane_mm.shape:
            raise ValueError("Control point arrays must have matching shapes")
        if any(len(np.unique(p, axis=0)) != len(p) for p in (pixels, plane_mm)):
            raise ValueError("Control points must be distinct")
        # Rank of the normalized DLT design checks more than simple collinearity.
        source, target = _normalize(pixels), _normalize(plane_mm)
        x, y = source.T
        u, v = target.T
        z, o = np.zeros(len(x)), np.ones(len(x))
        design = np.concatenate((
            np.column_stack((x, y, o, z, z, z, -u*x, -u*y, -u)),
            np.column_stack((z, z, z, x, y, o, -v*x, -v*y, -v)),
        ))
        if np.linalg.matrix_rank(design) < 8:
            raise ValueError("Degenerate calibration point configuration")
        matrix, _ = cv2.findHomography(pixels, plane_mm, method=0)
        if matrix is None:
            raise ValueError("Homography fit failed")
        calibration = cls(matrix)
        calibration.transform(pixels)
        return calibration

    def transform(self, pixels):
        """Map finite Nx2 pixel coordinates to Nx2 millimeter coordinates.

        Reject points at, near, or straddling the projective horizon. A single
        continuous object must occupy one finite side of that horizon.
        """
        pixels = _points(pixels, "pixels")
        homogeneous = np.column_stack((pixels, np.ones(len(pixels))))
        mapped = homogeneous @ self.pixel_to_plane.T
        denominator = mapped[:, 2]
        scale = np.abs(homogeneous) @ np.abs(self.pixel_to_plane[2])
        if (np.any(np.abs(denominator) <= 1e-12 * np.maximum(scale, 1e-300))
                or (denominator.min() < 0 < denominator.max())):
            raise ValueError("Points meet or straddle the projective horizon")
        result = mapped[:, :2] / denominator[:, None]
        if not np.isfinite(result).all():
            raise ValueError("Transformation produced nonfinite coordinates")
        return result

    def residuals_mm(self, pixels, plane_mm):
        """Return Euclidean errors for supplied control or held-out points."""
        pixels = _points(pixels, "pixels")
        plane_mm = _points(plane_mm, "plane_mm")
        if pixels.shape != plane_mm.shape:
            raise ValueError("Point arrays must have matching shapes")
        return np.linalg.norm(self.transform(pixels) - plane_mm, axis=1)
