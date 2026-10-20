import numpy as np
import pytest

from vision_inspection import PlanarCalibration


def project(points, matrix):
    homogeneous = np.column_stack((points, np.ones(len(points)))) @ matrix.T
    return homogeneous[:, :2] / homogeneous[:, 2:]


@pytest.mark.parametrize("matrix", [
    np.array([[4, 0, 160], [0, 3, 120], [0, 0, 1.0]]),
    np.array([[4, 0.7, 160], [-0.3, 3, 120], [0.004, -0.002, 1.0]]),
])
def test_calibration_exact_controls_and_independent_check_points(matrix):
    controls = np.array([[-30, -20], [30, -20], [30, 20], [-30, 20], [0, 0.]])
    pixels = project(controls, matrix)
    calibration = PlanarCalibration.from_correspondences(pixels, controls)
    checks = np.array([[-13.2, 7.1], [22.3, -9.8], [1.5, 12.3]])
    np.testing.assert_allclose(calibration.transform(project(checks, matrix)), checks, atol=5e-6)
    assert calibration.residuals_mm(pixels, controls).max() < 5e-6


def test_residuals_expose_bad_correspondence():
    pixels = np.array([[0, 0], [100, 0], [100, 100], [0, 100], [50, 50.]])
    plane = pixels / 10
    plane[-1] += (2, -1)
    calibration = PlanarCalibration.from_correspondences(pixels, plane)
    assert calibration.residuals_mm(pixels, plane).max() > 0.5


@pytest.mark.parametrize("points", [
    [[0, 0]] * 4,
    [[0, 0], [1, 1], [2, 2], [3, 3]],
    [[0, 0], [1, 0], [2, 0], [0, 1]],
    [[0, 0], [1, 0], [1, 1]],
    [[0, 0], [1, 0], [1, float("nan")], [0, 1]],
])
def test_reject_degenerate_controls(points):
    with pytest.raises(ValueError):
        PlanarCalibration.from_correspondences(points, points)


@pytest.mark.parametrize("matrix", [np.zeros((3, 3)), np.eye(2), np.full((3, 3), np.inf),
                                    [[0.1, 0, 1e7], [0, 0.1, -1e7], [0, 0, 1]]])
def test_reject_invalid_matrix(matrix):
    with pytest.raises(ValueError):
        PlanarCalibration(matrix)


@pytest.mark.parametrize("points", [[], [1, 2], [[np.nan, 0]], [[1, 2, 3]]])
def test_reject_invalid_transform_points(points):
    with pytest.raises(ValueError):
        PlanarCalibration(np.eye(3)).transform(points)


def test_horizon_and_matrix_scale_invariance():
    matrix = np.array([[1, 0, 0], [0, 1, 0], [0.01, 0, 1.]])
    calibration = PlanarCalibration(matrix)
    for points in ([[-100, 0]], [[-101, 0], [-99, 0]], [[-100 + 1e-12, 0]]):
        with pytest.raises(ValueError, match="horizon"):
            calibration.transform(points)
    points = [[0, 0], [20, 30]]
    np.testing.assert_allclose(calibration.transform(points),
                               PlanarCalibration(-1e-20 * matrix).transform(points))


def test_matrix_is_immutable_copy():
    matrix = np.eye(3)
    calibration = PlanarCalibration(matrix)
    matrix[0, 0] = 5
    assert calibration.transform([[1, 2]])[0, 0] == 1
    with pytest.raises(ValueError):
        calibration.pixel_to_plane.setflags(write=True)


def test_mismatched_correspondence_shapes():
    calibration = PlanarCalibration(np.eye(3))
    with pytest.raises(ValueError):
        calibration.residuals_mm([[0, 0]], [[0, 0], [1, 1]])
    with pytest.raises(ValueError):
        calibration.from_correspondences(np.zeros((4, 2)), np.zeros((5, 2)))
