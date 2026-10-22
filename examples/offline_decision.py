"""Run after installation: python examples/offline_decision.py."""

import numpy as np

from vision_inspection import (
    PlanarCalibration,
    classify_measurement,
    measure_rectangle,
)
from vision_inspection.synthetic import render_rectangle


def main():
    # Synthetic control points, independent of the inspected rectangle's size.
    calibration = PlanarCalibration.from_correspondences(
        [[40, 40], [280, 40], [280, 220], [40, 220]],
        [[-30, -20], [30, -20], [30, 20], [-30, 20]],
    )
    image = render_rectangle(
        image_shape=(240, 320),
        plane_to_pixel=np.array([[4, 0, 160], [0, 4.5, 130], [0, 0, 1.0]]),
        center_mm=(0, 0), size_mm=(40, 20), angle_deg=23, samples_per_axis=8,
    )
    measurement = measure_rectangle(image, calibration)
    length_limits_mm = (39.5, 40.5)
    width_limits_mm = (19.5, 20.5)
    zero_guard = classify_measurement(measurement, length_limits_mm, width_limits_mm)
    # Illustrative configured assumptions, NOT inferred from synthetic errors.
    guarded = classify_measurement(
        measurement, length_limits_mm, width_limits_mm,
        length_guard_mm=0.75, width_guard_mm=0.75,
    )
    print(f"Length: {measurement.length_mm:.3f} mm")
    print(f"Width:  {measurement.width_mm:.3f} mm")
    print(f"Length tolerance: {length_limits_mm} mm")
    print(f"Width tolerance:  {width_limits_mm} mm")
    print(f"Zero guards: {zero_guard.value}")
    print(f"Configured guards (length=0.75 mm, width=0.75 mm): {guarded.value}")


if __name__ == "__main__":
    main()
