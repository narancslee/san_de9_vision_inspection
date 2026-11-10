"""Separate-process DDS image-to-cell and freshness checks."""

import os
from pathlib import Path
import signal
import subprocess
import time

import rclpy
from ament_index_python.packages import get_package_prefix
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import Image

from inspection_interfaces.msg import CellState, InspectionDecision, RectangleMeasurement


def test_image_decision_cell_and_timeout():
    context = Context()
    rclpy.init(context=context, signal_handler_options=SignalHandlerOptions.NO)
    node = Node("cell_integration_observer", context=context)
    executor = SingleThreadedExecutor(context=context)
    executor.add_node(node)
    qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE,
                     durability=DurabilityPolicy.VOLATILE)
    images, measurements, decisions, states = [], [], [], []
    node.create_subscription(Image, "/inspection/image_raw", images.append, qos)
    node.create_subscription(RectangleMeasurement, "/inspection/rectangle_measurement",
                             measurements.append, qos)
    node.create_subscription(InspectionDecision, "/inspection/decision", decisions.append, qos)
    node.create_subscription(CellState, "/inspection/cell_state", states.append, qos)
    publisher = node.create_publisher(InspectionDecision, "/inspection/decision", qos)
    processes = []

    def until(predicate, seconds=25):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.1)
        assert predicate(), "DDS observation timeout"

    def stop(process, sig):
        process.send_signal(sig)
        output, _ = process.communicate(timeout=10)
        assert process.returncode == 0, output
        assert "Traceback" not in output, output

    try:
        for name in ("cell_node", "decision_node", "measurement_node", "synthetic_camera"):
            exe = str(Path(get_package_prefix("inspection_ros")) / "lib/inspection_ros" / name)
            processes.append(subprocess.Popen([exe], cwd="/tmp",
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, start_new_session=True))
        def complete_chain():
            return any(s.state == CellState.ACCEPT and s.reason == "fresh"
                and any(d.header == s.source_header and d.decision == InspectionDecision.ACCEPT
                    and any(m.header == d.header and any(i.header == m.header for i in images)
                            for m in measurements) for d in decisions) for s in states)
        until(complete_chain)
        stop(processes[3], signal.SIGINT)
        stop(processes[2], signal.SIGTERM)
        stop(processes[1], signal.SIGINT)
        until(lambda: states and states[-1].state == CellState.UNAVAILABLE
              and states[-1].reason == "stale", seconds=8)
        until(lambda: publisher.get_subscription_count() >= 1)
        def send(code, width=20.0):
            msg = InspectionDecision()
            msg.header.frame_id = "direct_cell_test"
            msg.header.stamp = node.get_clock().now().to_msg()
            msg.length_mm, msg.width_mm, msg.decision = 40.0, width, code
            publisher.publish(msg)
            return msg.header
        for code, state in ((InspectionDecision.REVIEW, CellState.REVIEW),
                            (InspectionDecision.REJECT, CellState.REJECT)):
            header = send(code)
            until(lambda: any(s.state == state and s.source_header == header for s in states))
        header = send(InspectionDecision.ACCEPT, float("nan"))
        until(lambda: states[-1].state == CellState.UNAVAILABLE and states[-1].reason == "invalid")
        assert not any(s.state == CellState.ACCEPT and s.source_header == header for s in states)
        header = send(InspectionDecision.ACCEPT)
        until(lambda: any(s.state == CellState.ACCEPT and s.source_header == header for s in states))
        stop(processes[0], signal.SIGTERM)
    finally:
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=5)
        executor.shutdown(timeout_sec=2)
        node.destroy_node()
        context.try_shutdown()
