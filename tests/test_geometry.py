"""Independent controls separating projection, rasterization and boundary handling."""

import cv2
import numpy as np
import pytest

from vision_inspection import PlanarCalibration, measure_rectangle
from vision_inspection.measurement import _boundary_crossings, _enclosing_rectangle
from vision_inspection.synthetic import render_rectangle


def test_exact_vector_boundary_transform_before_fit():
    # No image or rasterizer: a perspective rectangle becomes a quadrilateral.
    world = np.array([[-20, -10], [20, -10], [20, 10], [-20, 10.]])
    matrix = np.array([[4, 0.8, 140], [0.3, 3.5, 110], [0.008, -0.003, 1.]])
    homogeneous = np.column_stack((world, np.ones(4))) @ matrix.T
    pixels = homogeneous[:, :2] / homogeneous[:, 2:]
    calibration = PlanarCalibration(np.linalg.inv(matrix))
    measured = _enclosing_rectangle(calibration.transform(pixels))
    assert measured.length_mm == pytest.approx(40, abs=1e-5)
    assert measured.width_mm == pytest.approx(20, abs=1e-5)
    # Deliberately wrong control, NOT recovered prototype code: fit first.
    pixel_box = cv2.boxPoints(cv2.minAreaRect(pixels.astype(np.float32)))
    wrong = _enclosing_rectangle(calibration.transform(pixel_box))
    assert wrong.width_mm - 20 > 1.0


@pytest.mark.parametrize("scale", [0.1, 0.25, 0.7])
def test_binary_step_pixel_centers_are_not_pixel_footprint_edges(scale):
    image = np.zeros((60, 100), np.uint8)
    image[15:35, 20:60] = 255
    calibration = PlanarCalibration(np.diag([scale, scale, 1]))
    measured = measure_rectangle(image, calibration)
    assert measured.length_mm == pytest.approx(40 * scale, abs=1e-5)
    assert measured.width_mm == pytest.approx(20 * scale, abs=1e-5)
    contour = cv2.findContours(image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0][0]
    centers = calibration.transform(contour[:, 0, :])
    old = _enclosing_rectangle(centers)
    assert old.width_mm == pytest.approx(19 * scale, abs=1e-5)
    assert old.length_mm == pytest.approx(39 * scale, abs=1e-5)


def test_crossing_uses_intensity_interpolation_without_dimension_offset():
    image = np.zeros((10, 12), dtype=float)
    image[3:7, 4:8] = 200
    mask = (image > 50).astype(np.uint8)
    boundary = _boundary_crossings(image, mask, 50)
    np.testing.assert_allclose(boundary.min(axis=0), [3.25, 2.25])
    np.testing.assert_allclose(boundary.max(axis=0), [7.75, 6.75])


@pytest.mark.parametrize("phase", [0.0, 0.1, 0.35, 0.7, 0.95])
def test_center_sample_raster_error_is_bounded_not_zero(phase):
    # Analytically count center samples, independently of the renderer.
    scale = 0.25
    left, top = 20 + phase, 15 + phase
    right, bottom = left + 40.3, top + 20.7
    y, x = np.indices((60, 100))
    image = (255 * ((x >= left) & (x <= right) & (y >= top) & (y <= bottom))).astype(np.uint8)
    result = measure_rectangle(image, PlanarCalibration(np.diag([scale, scale, 1])))
    # Each sampled end can move by <=0.5 px; the side error is <=1 px.
    assert abs(result.length_mm - 40.3 * scale) <= scale + 1e-5
    assert abs(result.width_mm - 20.7 * scale) <= scale + 1e-5


def test_large_plane_offset_does_not_destroy_small_dimensions():
    image = np.zeros((60, 100), np.uint8)
    image[15:35, 20:60] = 255
    calibration = PlanarCalibration([[0.1, 0, 1e6], [0, 0.1, -1e6], [0, 0, 1]])
    result = measure_rectangle(image, calibration)
    assert result.length_mm == pytest.approx(4, abs=1e-5)
    assert result.width_mm == pytest.approx(2, abs=1e-5)


def test_raster_fixture_has_independent_analytic_axis_control():
    image = render_rectangle(image_shape=(60, 100), plane_to_pixel=np.eye(3),
                             center_mm=(39.5, 24.5), size_mm=(40, 20), samples_per_axis=8)
    expected = np.zeros_like(image)
    expected[15:35, 20:60] = 255
    np.testing.assert_array_equal(image, expected)


def test_rotated_perspective_raster_sweep():
    errors = []
    for scale in (3.0, 4.0, 5.0):
        for perspective in (0.0, 0.002):
            matrix = np.array([[scale, 0.3, 160], [0.1, scale, 120],
                               [perspective, -perspective/2, 1.]])
            calibration = PlanarCalibration(np.linalg.inv(matrix))
            for angle in (0, 17, 43, 78):
                for phase in (0.0, 0.2, 0.4, 0.6, 0.8):
                    image = render_rectangle(
                        image_shape=(240, 320), plane_to_pixel=matrix,
                        center_mm=(phase / scale, -phase / scale), size_mm=(32, 16),
                        angle_deg=angle, samples_per_axis=4,
                    )
                    result = measure_rectangle(image, calibration)
                    errors.append([result.length_mm - 32, result.width_mm - 16])
    errors = np.array(errors)
    # Conservative 2-pixel allowance at the coarsest nominal 3 px/mm.
    # This is a numerical regression bound, not a metrology specification.
    assert np.max(np.abs(errors)) < 2/3
    print("\n120-case synthetic sweep (length, width), mm:")
    print("bias:", np.mean(errors, axis=0))
    print("RMSE:", np.sqrt(np.mean(errors**2, axis=0)))
    print("max_abs:", np.max(np.abs(errors), axis=0))
