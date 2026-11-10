"""Publish freshness-gated simulated cell state from ROS decisions."""

import signal
import sys
import time

import rclpy
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.clock import Clock, ClockType
from rclpy.exceptions import InvalidParameterTypeException, InvalidParameterValueException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions

from inspection_interfaces.msg import CellState, InspectionDecision
from inspection_ros.cell_logic import CellLogic


class CellNode(Node):
    def __init__(self, **kwargs):
        super().__init__("cell_node", **kwargs)
        try:
            timeout = self.declare_parameter(
                "timeout_seconds", 3.0, ParameterDescriptor(read_only=True)).value
            self.logic = CellLogic(timeout)
            qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=1,
                             reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.VOLATILE)
            self.publisher = self.create_publisher(CellState, "/inspection/cell_state", qos)
            self.subscription = self.create_subscription(
                InspectionDecision, "/inspection/decision", self.on_decision, qos)
            self.steady_clock = Clock(clock_type=ClockType.STEADY_TIME)
            self.timer = self.create_timer(0.1, self.tick, clock=self.steady_clock)
        except Exception:
            self.destroy_node()
            raise

    def on_decision(self, msg):
        stamp = msg.header.stamp
        valid_stamp = 0 <= stamp.nanosec < 1000000000
        stamp_ns = stamp.sec * 1000000000 + stamp.nanosec if valid_stamp else 0
        self.logic.update(int(msg.decision), msg.length_mm, msg.width_mm, stamp_ns,
                          self.get_clock().now().nanoseconds, time.monotonic(), msg.header)
        self.publish_state()

    def tick(self):
        self.logic.expire(self.get_clock().now().nanoseconds, time.monotonic())
        self.publish_state()

    def publish_state(self):
        result = CellState()
        result.state = self.logic.state
        result.reason = self.logic.reason
        if self.logic.header is not None:
            result.source_header = self.logic.header
        self.publisher.publish(result)


def main(args=None):
    stopping = False
    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True
    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    node = None
    try:
        rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
        node = CellNode()
        while not stopping and rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.2)
    except (ValueError, InvalidParameterTypeException, InvalidParameterValueException) as error:
        print(f"cell_node: {error}", file=sys.stderr)
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
