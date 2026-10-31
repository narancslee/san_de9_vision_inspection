"""Measure calibrated mono8 images without making a conformity decision."""

import signal
import sys

import numpy as np
import rclpy
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.exceptions import InvalidParameterTypeException, InvalidParameterValueException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import Image
from inspection_interfaces.msg import RectangleMeasurement
from vision_inspection import PlanarCalibration, measure_rectangle


class CalibrationError(ValueError):
    """Invalid startup calibration or image geometry."""


def make_calibration(width, height, frame_id, pixels, plane):
    """Validate image geometry and fit paired flattened control points."""
    if type(width) is not int or type(height) is not int or min(width, height) < 3:
        raise CalibrationError("image_width and image_height must be integers >= 3")
    if not isinstance(frame_id, str) or not frame_id.strip():
        raise CalibrationError("frame_id must be a nonempty string")
    try:
        pixels = np.asarray(pixels, dtype=np.float64).reshape(-1, 2)
        plane = np.asarray(plane, dtype=np.float64).reshape(-1, 2)
        if (not np.isfinite(pixels).all() or np.any(pixels < 0)
                or np.any(pixels[:, 0] >= width) or np.any(pixels[:, 1] >= height)):
            raise ValueError("pixel_points must be finite and inside the configured image")
        calibration = PlanarCalibration.from_correspondences(pixels, plane)
        calibration.transform([[0, 0], [width - 1, 0],
                               [width - 1, height - 1], [0, height - 1]])
        return calibration
    except (ValueError, TypeError, OverflowError) as error:
        raise CalibrationError(f"invalid calibration: {error}") from error


def unpack_image(message, width, height, frame_id):
    """Validate ROS storage and return the pixels without any row padding."""
    if (message.width, message.height) != (width, height):
        raise ValueError(f"image size {message.width}x{message.height} does not match {width}x{height}")
    if message.header.frame_id != frame_id:
        raise ValueError(f"image frame_id {message.header.frame_id!r} does not match {frame_id!r}")
    if message.encoding != "mono8":
        raise ValueError(f"expected mono8 encoding, got {message.encoding!r}")
    if message.step < width:
        raise ValueError("image step is smaller than width")
    if len(message.data) != message.step * height:
        raise ValueError("image data length does not match height * step")
    return np.frombuffer(message.data, dtype=np.uint8).reshape(height, message.step)[:, :width]


class MeasurementNode(Node):
    def __init__(self, **kwargs):
        super().__init__("measurement_node", **kwargs)
        try:
            descriptor = ParameterDescriptor(read_only=True)
            def param(name, default):
                return self.declare_parameter(name, default, descriptor).value
            self._width = param("image_width", 320)
            self._height = param("image_height", 240)
            self._frame = param("frame_id", "inspection_camera_optical_frame")
            pixels = param("pixel_points", [40.0, 40.0, 280.0, 40.0, 280.0, 220.0, 40.0, 220.0])
            plane = param("plane_points_mm", [-30.0, -20.0, 30.0, -20.0, 30.0, 20.0, -30.0, 20.0])
            self._calibration = make_calibration(self._width, self._height, self._frame, pixels, plane)
            qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=1,
                             reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.VOLATILE)
            self._publisher = self.create_publisher(RectangleMeasurement, "/inspection/rectangle_measurement", qos)
            self._subscription = self.create_subscription(Image, "/inspection/image_raw", self._on_image, qos)
        except Exception:
            self.destroy_node()
            raise

    def _on_image(self, message):
        try:
            image = unpack_image(message, self._width, self._height, self._frame)
            result = measure_rectangle(image, self._calibration)
        except ValueError as error:
            self.get_logger().warning(f"Image not measured: {error}")
            return
        output = RectangleMeasurement()
        output.header = message.header
        output.length_mm = result.length_mm
        output.width_mm = result.width_mm
        self._publisher.publish(output)


def main(args=None):
    stopping = False
    def request_stop(signum, frame):
        nonlocal stopping
        stopping = True
    previous = {sig: signal.signal(sig, request_stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    node = None
    try:
        rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
        node = MeasurementNode()
        while not stopping and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.2)
    except (CalibrationError, InvalidParameterTypeException, InvalidParameterValueException) as error:
        print(f"measurement_node: {error}", file=sys.stderr)
        return 2
    finally:
        try:
            if node is not None:
                node.destroy_node()
            rclpy.try_shutdown()
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
    return 0
