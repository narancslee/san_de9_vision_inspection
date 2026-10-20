"""Separate deterministic test support; never imported by the measurement code."""

import numpy as np


def render_rectangle(*, image_shape, plane_to_pixel, center_mm, size_mm,
                     angle_deg=0.0, samples_per_axis=4):
    """Render area coverage by inverse-mapping regular subpixel samples.

    Pixel centers are integers; pixel footprints extend +/-0.5. size_mm is
    (local-x side, local-y side). White foreground, black background, no blur,
    noise or lens distortion. This is a fixture, not a camera simulator.
    """
    if (len(image_shape) != 2 or any(type(n) is not int or n < 3 for n in image_shape)
            or type(samples_per_axis) is not int or samples_per_axis < 1):
        raise ValueError("Use a positive integer image shape and sampling count")
    matrix = np.asarray(plane_to_pixel, dtype=np.float64)
    center = np.asarray(center_mm, dtype=np.float64)
    size = np.asarray(size_mm, dtype=np.float64)
    if (matrix.shape != (3, 3) or not np.isfinite(matrix).all()
            or np.linalg.matrix_rank(matrix) != 3
            or center.shape != (2,) or not np.isfinite(center).all()
            or size.shape != (2,) or not np.isfinite(size).all() or (size <= 0).any()
            or not np.isfinite(angle_deg)):
        raise ValueError("Invalid rendering geometry")
    inverse = np.linalg.inv(matrix)
    y, x = np.indices(image_shape, dtype=np.float64)
    coverage = np.zeros(image_shape, dtype=np.float64)
    angle = np.deg2rad(angle_deg)
    cosine, sine = np.cos(angle), np.sin(angle)
    offsets = (np.arange(samples_per_axis) + 0.5) / samples_per_axis - 0.5
    for dy in offsets:
        for dx in offsets:
            px, py = x + dx, y + dy
            w = inverse[2, 0]*px + inverse[2, 1]*py + inverse[2, 2]
            if np.any(np.abs(w) < 1e-12) or w.min() < 0 < w.max():
                raise ValueError("Image meets or straddles the projective horizon")
            world_x = (inverse[0, 0]*px + inverse[0, 1]*py + inverse[0, 2])/w - center[0]
            world_y = (inverse[1, 0]*px + inverse[1, 1]*py + inverse[1, 2])/w - center[1]
            local_x = cosine*world_x + sine*world_y
            local_y = -sine*world_x + cosine*world_y
            coverage += (np.abs(local_x) <= size[0]/2) & (np.abs(local_y) <= size[1]/2)
    return np.rint(255 * coverage / samples_per_axis**2).astype(np.uint8)
