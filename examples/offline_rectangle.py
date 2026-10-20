"""Run after installation: python examples/offline_rectangle.py."""

import numpy as np

from vision_inspection import PlanarCalibration, measure_rectangle
from vision_inspection.synthetic import render_rectangle


def main():
    # Synthetic control points, independent of the inspected rectangle's size.
    pixels = np.array([[40, 40], [280, 40], [280, 220], [40, 220]], dtype=float)
    plane_mm = np.array([[-30, -20], [30, -20], [30, 20], [-30, 20]], dtype=float)
    calibration = PlanarCalibration.from_correspondences(pixels, plane_mm)
    image = render_rectangle(
        image_shape=(240, 320),
        plane_to_pixel=np.array([[4, 0, 160], [0, 4.5, 130], [0, 0, 1.0]]),
        center_mm=(0, 0), size_mm=(40, 20), angle_deg=23, samples_per_axis=8,
    )
    result = measure_rectangle(image, calibration)
    print(f"Length: {result.length_mm:.3f} mm")
    print(f"Width:  {result.width_mm:.3f} mm")


if __name__ == "__main__":
    main()
