"""Unit contracts using real Humble messages, parameters and clocks."""

from unittest.mock import Mock

import numpy as np
import pytest
import rclpy
from rclpy.context import Context
from rclpy.parameter import Parameter
from rclpy.signals import SignalHandlerOptions

from inspection_ros import synthetic_camera as camera
from vision_inspection.synthetic import render_rectangle


@pytest.fixture
def context():
    context = Context()
    rclpy.init(context=context, signal_handler_options=SignalHandlerOptions.NO)
    yield context
    context.try_shutdown()


def test_fixture_and_complete_image_contract():
    expected = render_rectangle(
        image_shape=(240, 320),
        plane_to_pixel=np.array([[4, 0, 160], [0, 4.5, 130], [0, 0, 1.0]]),
        center_mm=(0, 0), size_mm=(40, 20), angle_deg=23, samples_per_axis=8,
    )
    image = camera.fixture_image()
    message = camera.pack_image(image)
    assert (message.height, message.width, message.step) == (240, 320, 320)
    assert message.encoding == "mono8"
    assert message.is_bigendian == 0
    assert message.header.frame_id == "inspection_camera_optical_frame"
    assert len(message.data) == 76800
    assert bytes(message.data) == expected.tobytes(order="C")
    assert np.array_equal(image, expected)


def test_noncontiguous_image_is_packed_in_row_order_and_copied():
    source = np.arange(48, dtype=np.uint8).reshape(6, 8)[::2, ::-2]
    expected = bytes(int(value) for row in source for value in row)
    message = camera.pack_image(source)
    source[:] = 0
    assert (message.height, message.width, message.step) == (3, 4, 4)
    assert bytes(message.data) == expected


@pytest.mark.parametrize("image", [
    [[0]], np.zeros((2, 2), dtype=float), np.zeros((2, 2, 1), dtype=np.uint8),
    np.zeros((0, 2), dtype=np.uint8),
])
def test_invalid_image_is_rejected(image):
    with pytest.raises(ValueError):
        camera.pack_image(image)


@pytest.mark.parametrize("value", [0.1, 1.0, 10.0])
def test_valid_rate(value):
    assert camera.validate_publish_rate(value) == value


@pytest.mark.parametrize("value", [
    0.0, -1.0, 0.099999999, 10.000000001, float("nan"),
    float("inf"), -float("inf"), 1, True, "1.0", None,
])
def test_invalid_rate(value):
    with pytest.raises(camera.PublishRateError, match="finite DOUBLE"):
        camera.validate_publish_rate(value)


@pytest.mark.parametrize("value", [None, 0.1, 10.0])
def test_startup_default_bounds_and_read_only(context, value):
    overrides = [] if value is None else [Parameter("publish_rate_hz", value=value)]
    node = camera.SyntheticCamera(context=context, parameter_overrides=overrides)
    try:
        expected = 1.0 if value is None else value
        assert node.get_parameter("publish_rate_hz").value == expected
        assert node._timer.timer_period_ns == round(1e9 / expected)
        descriptor = node.describe_parameter("publish_rate_hz")
        assert descriptor.read_only
        assert descriptor.floating_point_range[0].from_value == 0.1
        assert descriptor.floating_point_range[0].to_value == 10.0
        result = node.set_parameters([Parameter("publish_rate_hz", value=2.0)])[0]
        assert not result.successful
        assert "read-only" in result.reason
        assert node.get_parameter("publish_rate_hz").value == expected
    finally:
        node.destroy_node()


@pytest.mark.parametrize("value", [
    0.0, 0.099999999, 10.000000001, float("nan"), float("inf"),
    -float("inf"), 1, True, "1.0",
])
def test_invalid_startup_parameter(context, value):
    with pytest.raises((camera.PublishRateError, camera.InvalidParameterTypeException,
                        camera.InvalidParameterValueException), match="publish_rate_hz"):
        camera.SyntheticCamera(
            context=context, parameter_overrides=[Parameter("publish_rate_hz", value=value)],
        )


def test_generate_once_and_stamp_every_publish(context, monkeypatch):
    renderer = Mock(wraps=camera.fixture_image)
    monkeypatch.setattr(camera, "fixture_image", renderer)
    node = camera.SyntheticCamera(context=context)
    try:
        publisher = Mock()
        node._publisher = publisher
        times = [rclpy.time.Time(nanoseconds=value) for value in (1234567890, 2345678901)]
        monkeypatch.setattr(node.get_clock(), "now", Mock(side_effect=times))
        stamps, pixels = [], []

        def capture(message):
            stamps.append(message.header.stamp.sec * 10**9 + message.header.stamp.nanosec)
            pixels.append(bytes(message.data))

        publisher.publish.side_effect = capture
        node._publish_image()
        node._publish_image()
        assert stamps == [1234567890, 2345678901]
        assert pixels[0] == pixels[1]
        renderer.assert_called_once_with()
    finally:
        node.destroy_node()


def test_real_callback_failure_is_not_hidden(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("deliberate callback failure")

    monkeypatch.setattr(rclpy, "spin_once", fail)
    with pytest.raises(RuntimeError, match="deliberate callback failure"):
        camera.main(args=[])
    assert not rclpy.ok()
