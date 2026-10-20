import numpy as np
import pytest

from vision_inspection import PlanarCalibration, measure_rectangle
from vision_inspection.synthetic import render_rectangle


def valid_image():
    image = np.zeros((60, 100), np.uint8)
    image[15:35, 20:60] = 255
    return image


@pytest.mark.parametrize("image", [np.zeros((2, 2), np.uint8), np.zeros((5, 5, 3), np.uint8),
                                    np.zeros((5, 5), float), np.array([]),
                                    np.zeros((5, 5), np.uint8), np.full((5, 5), 255, np.uint8)])
def test_reject_invalid_or_empty_image(image):
    with pytest.raises(ValueError):
        measure_rectangle(image, PlanarCalibration(np.eye(3)))


@pytest.mark.parametrize("threshold", [np.nan, np.inf, -1, 255, [127.5], "127", None, 1j, True])
def test_reject_invalid_threshold(threshold):
    with pytest.raises(ValueError):
        measure_rectangle(valid_image(), PlanarCalibration(np.eye(3)), threshold=threshold)


@pytest.mark.parametrize("defect", ["hole", "second_object", "clipped", "line", "single_pixel"])
def test_reject_unsupported_foreground(defect):
    image = valid_image()
    if defect == "hole":
        image[20:25, 30:40] = 0
    elif defect == "second_object":
        image[40:45, 70:75] = 255
    elif defect == "clipped":
        image[:20, 20:60] = 255
    else:
        image[:] = 0
        image[20, 20:40 if defect == "line" else 21] = 255
    with pytest.raises(ValueError):
        measure_rectangle(image, PlanarCalibration(np.eye(3)))


def test_reject_horizon_through_object():
    with pytest.raises(ValueError, match="horizon"):
        measure_rectangle(valid_image(), PlanarCalibration([[1, 0, 0], [0, 1, 0], [1, 0, -40]]))


def test_reject_missing_calibration():
    with pytest.raises(ValueError, match="calibration"):
        measure_rectangle(valid_image(), None)


@pytest.mark.parametrize("overrides", [
    {"size_mm": (-1, 20)}, {"center_mm": (np.nan, 0)}, {"samples_per_axis": 0},
    {"plane_to_pixel": np.zeros((3, 3))}, {"angle_deg": np.inf}, {"image_shape": (1, 5)},
])
def test_fixture_rejects_invalid_geometry(overrides):
    options = dict(image_shape=(60, 100), plane_to_pixel=np.eye(3), center_mm=(40, 25), size_mm=(20, 10))
    options.update(overrides)
    with pytest.raises(ValueError):
        render_rectangle(**options)
