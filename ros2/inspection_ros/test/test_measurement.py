"""Measurement adapter contracts using Humble messages and parameters."""
from unittest.mock import Mock

import numpy as np
import pytest
import rclpy
from rclpy.context import Context
from rclpy.parameter import Parameter
from rclpy.signals import SignalHandlerOptions

from inspection_ros import measurement_node as measurement
from inspection_ros.synthetic_camera import fixture_image, pack_image

PIXELS = [40., 40., 280., 40., 280., 220., 40., 220.]
PLANE = [-30., -20., 30., -20., 30., 20., -30., 20.]


@pytest.fixture
def node():
    context = Context()
    rclpy.init(context=context, signal_handler_options=SignalHandlerOptions.NO)
    node = measurement.MeasurementNode(context=context)
    node._publisher = Mock()
    yield node
    node.destroy_node()
    context.try_shutdown()


def test_calibration_and_image_geometry():
    cal = measurement.make_calibration(320, 240, 'frame', PIXELS, PLANE)
    np.testing.assert_allclose(cal.transform([[160, 130]]), [[0, 0]], atol=1e-8)


@pytest.mark.parametrize('width,height,frame,pixels,plane', [
    (2, 240, 'frame', PIXELS, PLANE), (320, 0, 'frame', PIXELS, PLANE),
    (320, 240, '', PIXELS, PLANE), (320, 240, 'frame', [1., 2., 3.], PLANE),
    (320, 240, 'frame', PIXELS, PLANE[:-2]),
    (320, 240, 'frame', [400., 40.] + PIXELS[2:], PLANE),
    (320, 240, 'frame', [40., 40.] * 4, PLANE),
    (320, 240, 'frame', PIXELS, [float('nan')] + PLANE[1:]),
])
def test_invalid_calibration(width, height, frame, pixels, plane):
    with pytest.raises(measurement.CalibrationError):
        measurement.make_calibration(width, height, frame, pixels, plane)


def test_invalid_startup_and_read_only(node):
    assert not node.set_parameters([Parameter('image_width', value=100)])[0].successful
    with pytest.raises(measurement.CalibrationError, match='frame_id'):
        measurement.MeasurementNode(context=node.context, parameter_overrides=[Parameter('frame_id', value='')])


def test_header_units_padding_and_recovery(node):
    image = pack_image(fixture_image())
    image.header.stamp.sec = 123
    image.header.stamp.nanosec = 456
    rows = np.frombuffer(image.data, dtype=np.uint8).reshape(240, 320)
    padded = np.pad(rows, ((0, 0), (0, 7)), constant_values=255)
    image.step = 327
    image.data = padded.tobytes()
    node._on_image(image)
    result = node._publisher.publish.call_args.args[0]
    assert result.header == image.header
    assert result.length_mm == pytest.approx(40.042, abs=.001)
    assert result.width_mm == pytest.approx(20.042, abs=.001)
    assert result.length_mm >= result.width_mm
    node._publisher.reset_mock()
    image.data = image.data[:-1]
    node._on_image(image)
    node._publisher.publish.assert_not_called()
    node._on_image(pack_image(fixture_image()))
    node._publisher.publish.assert_called_once()


@pytest.mark.parametrize('mutation', ['width', 'height', 'frame', 'encoding', 'step', 'short', 'extra', 'empty', 'border'])
def test_bad_images_do_not_publish(node, mutation):
    image = pack_image(fixture_image())
    if mutation == 'width': image.width -= 1
    elif mutation == 'height': image.height -= 1
    elif mutation == 'frame': image.header.frame_id = 'wrong'
    elif mutation == 'encoding': image.encoding = 'rgb8'
    elif mutation == 'step': image.step = 319
    elif mutation == 'short': image.data = image.data[:-1]
    elif mutation == 'extra': image.data = bytes(image.data) + b'\0'
    elif mutation == 'empty': image.data = bytes(320 * 240)
    else: image.data = bytes([255]) * (320 * 240)
    node._on_image(image)
    node._publisher.publish.assert_not_called()
