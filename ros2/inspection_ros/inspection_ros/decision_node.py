"""Classify ROS measurements using the offline dimensional decision rule."""

import signal
import sys

import rclpy
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.exceptions import InvalidParameterTypeException, InvalidParameterValueException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions

from inspection_interfaces.msg import InspectionDecision as DecisionMessage
from inspection_interfaces.msg import RectangleMeasurement as MeasurementMessage
from vision_inspection import (
    InspectionDecision, RectangleMeasurement, classify_measurement,
)


class ConfigurationError(ValueError):
    """Invalid startup decision parameters."""


class DecisionNode(Node):
    def __init__(self, **kwargs):
        super().__init__("decision_node", **kwargs)
        try:
            descriptor = ParameterDescriptor(read_only=True)
            def param(name, default):
                return self.declare_parameter(name, default, descriptor).value
            self._length_limits = (param("length_min_mm", 39.0), param("length_max_mm", 41.0))
            self._width_limits = (param("width_min_mm", 19.0), param("width_max_mm", 21.0))
            self._length_guard = param("length_guard_mm", 0.1)
            self._width_guard = param("width_guard_mm", 0.1)
            # Reuse the offline validator for the entire configuration. No geometry
            # is invented: corners are unused by the classifier.
            try:
                self._classify(RectangleMeasurement(length_mm=1.0, width_mm=1.0, corners_mm=()))
            except ValueError as error:
                raise ConfigurationError(f"invalid decision configuration: {error}") from error
            qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=1,
                             reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.VOLATILE)
            self._publisher = self.create_publisher(DecisionMessage, "/inspection/decision", qos)
            self._subscription = self.create_subscription(
                MeasurementMessage, "/inspection/rectangle_measurement", self._on_measurement, qos)
        except Exception:
            self.destroy_node()
            raise

    def _classify(self, measurement):
        return classify_measurement(
            measurement, self._length_limits, self._width_limits,
            length_guard_mm=self._length_guard, width_guard_mm=self._width_guard)

    def _on_measurement(self, message):
        try:
            measurement = RectangleMeasurement(
                length_mm=message.length_mm, width_mm=message.width_mm, corners_mm=())
            decision = self._classify(measurement)
            codes = {
                InspectionDecision.ACCEPT: DecisionMessage.ACCEPT,
                InspectionDecision.REVIEW: DecisionMessage.REVIEW,
                InspectionDecision.REJECT: DecisionMessage.REJECT,
            }
            if decision not in codes:
                raise ValueError(f"unknown classifier result: {decision!r}")
            code = codes[decision]
        except (ValueError, TypeError) as error:
            self.get_logger().warning(f"Measurement not classified: {error}")
            return
        output = DecisionMessage()
        output.header = message.header
        output.decision = code
        output.length_mm = message.length_mm
        output.width_mm = message.width_mm
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
        node = DecisionNode()
        while not stopping and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.2)
    except (ConfigurationError, InvalidParameterTypeException, InvalidParameterValueException) as error:
        print(f"decision_node: {error}", file=sys.stderr)
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
