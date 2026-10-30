"""Publish one cached offline fixture; no measurement or decision is made."""

import math
import signal
import sys

import numpy as np
import rclpy
from rcl_interfaces.msg import FloatingPointRange, ParameterDescriptor
from rclpy.exceptions import InvalidParameterTypeException, InvalidParameterValueException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import Image

from vision_inspection.synthetic import render_rectangle


FRAME_ID = "inspection_camera_optical_frame"
TOPIC = "/inspection/image_raw"


class PublishRateError(ValueError):
    """An invalid startup-only publish rate."""


def validate_publish_rate(value):
    """Require a ROS DOUBLE, including exact closed bounds and finiteness."""
    if type(value) is not float or not math.isfinite(value) or not 0.1 <= value <= 10.0:
        raise PublishRateError(
            "publish_rate_hz must be a finite DOUBLE in [0.1, 10.0] Hz "
            "(use a decimal, for example 1.0)"
        )
    return value


def fixture_image():
    """Use the same renderer and geometry as examples/offline_rectangle.py."""
    return render_rectangle(
        image_shape=(240, 320),
        plane_to_pixel=np.array([[4, 0, 160], [0, 4.5, 130], [0, 0, 1.0]]),
        center_mm=(0, 0), size_mm=(40, 20), angle_deg=23, samples_per_axis=8,
    )


def pack_image(image):
    """Copy a 2D uint8 image into complete row-major mono8 ROS storage."""
    if not isinstance(image, np.ndarray) or image.ndim != 2 or image.dtype != np.uint8:
        raise ValueError("image must be a 2D uint8 NumPy array")
    height, width = image.shape
    if height == 0 or width == 0:
        raise ValueError("image dimensions must be positive")
    message = Image()
    message.header.frame_id = FRAME_ID
    message.height = height
    message.width = width
    message.encoding = "mono8"
    message.is_bigendian = 0
    message.step = width
    message.data = image.tobytes(order="C")
    return message


class SyntheticCamera(Node):
    """Generate once and publish identical pixels with fresh ROS timestamps."""

    def __init__(self, **kwargs):
        super().__init__("synthetic_camera", **kwargs)
        try:
            parameter = self.declare_parameter(
                "publish_rate_hz", 1.0,
                ParameterDescriptor(
                    description="Startup-only rate in Hz; finite DOUBLE in [0.1, 10.0]",
                    read_only=True,
                    floating_point_range=[FloatingPointRange(
                        from_value=0.1, to_value=10.0, step=0.0,
                    )],
                ),
            )
            rate = validate_publish_rate(parameter.value)
            self._image = pack_image(fixture_image())
            self._publisher = self.create_publisher(
                Image, TOPIC,
                QoSProfile(
                    history=HistoryPolicy.KEEP_LAST, depth=1,
                    reliability=ReliabilityPolicy.RELIABLE,
                    durability=DurabilityPolicy.VOLATILE,
                ),
            )
            self._timer = self.create_timer(1.0 / rate, self._publish_image)
        except Exception:
            self.destroy_node()
            raise

    def _publish_image(self):
        self._image.header.stamp = self.get_clock().now().to_msg()
        self._publisher.publish(self._image)


def main(args=None):
    """Stop on SIGINT/SIGTERM before destroying the still-valid ROS context."""
    stopping = False

    def request_stop(signum, frame):
        nonlocal stopping
        stopping = True

    previous_handlers = {
        sig: signal.signal(sig, request_stop) for sig in (signal.SIGINT, signal.SIGTERM)
    }
    node = None
    try:
        # Shutdown is deferred to finally, avoiding a signal invalidating the
        # context halfway through a publish callback. spin_once has a bound.
        rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
        node = SyntheticCamera()
        while not stopping and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.2)
    except (PublishRateError, InvalidParameterTypeException,
            InvalidParameterValueException) as error:
        print(f"synthetic_camera: {error}", file=sys.stderr)
        return 2
    finally:
        try:
            if node is not None:
                node.destroy_node()
            rclpy.try_shutdown()
        finally:
            for sig, handler in previous_handlers.items():
                signal.signal(sig, handler)
    return 0
