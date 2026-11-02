"""Installed decision node and independent DDS image/measurement processes."""
import os
from pathlib import Path
import signal
import subprocess
import time

import pytest
import rclpy
from ament_index_python.packages import get_package_prefix
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import Image
from inspection_interfaces.msg import InspectionDecision, RectangleMeasurement


def spin_until(executor, predicate, timeout=20):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        executor.spin_once(timeout_sec=.1)
    assert predicate(), 'DDS timeout'


def stop(process, sig):
    process.send_signal(sig)
    output, _ = process.communicate(timeout=10)
    assert process.returncode == 0, output
    assert 'Traceback' not in output, output
    return output


def test_image_chain_and_direct_measurements():
    context = Context()
    rclpy.init(context=context, signal_handler_options=SignalHandlerOptions.NO)
    node = Node('decision_process_observer', context=context)
    executor = SingleThreadedExecutor(context=context)
    executor.add_node(node)
    qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE)
    images, measurements, decisions = [], [], []
    node.create_subscription(Image, '/inspection/image_raw', images.append, qos)
    node.create_subscription(RectangleMeasurement, '/inspection/rectangle_measurement', measurements.append, qos)
    node.create_subscription(InspectionDecision, '/inspection/decision', decisions.append, qos)
    publisher = node.create_publisher(RectangleMeasurement, '/inspection/rectangle_measurement', qos)
    processes = []
    try:
        for name in ('decision_node', 'measurement_node', 'synthetic_camera'):
            executable = str(Path(get_package_prefix('inspection_ros')) / 'lib/inspection_ros' / name)
            process = subprocess.Popen([executable], cwd='/tmp',
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
            processes.append(process)
        spin_until(executor, lambda: any(d.decision == InspectionDecision.ACCEPT and
            any(m.header == d.header and m.length_mm == d.length_mm and m.width_mm == d.width_mm
                and any(i.header == m.header for i in images) for m in measurements) for d in decisions))
        match = next(d for d in decisions if any(m.header == d.header and
            m.length_mm == d.length_mm and m.width_mm == d.width_mm and
            any(i.header == m.header for i in images) for m in measurements))
        assert match.decision == InspectionDecision.ACCEPT
        print(f'Full image chain ACCEPT: {match.length_mm:.6f} x {match.width_mm:.6f} mm; header={match.header}')
        # Stop the camera and meter before sending uniquely identified direct measurements.
        stop(processes[2], signal.SIGINT)
        stop(processes[1], signal.SIGTERM)
        spin_until(executor, lambda: publisher.get_subscription_count() >= 1)
        for stamp, length in [(101, 39.), (102, 42.), (103, float('nan')), (104, 40.)]:
            msg = RectangleMeasurement(length_mm=length, width_mm=20.)
            msg.header.frame_id = 'direct_test'; msg.header.stamp.sec = stamp
            publisher.publish(msg)
            if stamp != 103:
                spin_until(executor, lambda: any(d.header.stamp.sec == stamp and d.header.frame_id == 'direct_test' for d in decisions))
            else:
                end = time.monotonic() + 1
                while time.monotonic() < end: executor.spin_once(timeout_sec=.1)
        direct = [d for d in decisions if d.header.frame_id == 'direct_test']
        assert [(d.header.stamp.sec, d.decision) for d in direct] == [
            (101, InspectionDecision.REVIEW), (102, InspectionDecision.REJECT),
            (104, InspectionDecision.ACCEPT)]
        assert [(d.length_mm, d.width_mm) for d in direct] == [(39., 20.), (42., 20.), (40., 20.)]
        print('Direct measurement: REVIEW, REJECT, invalid (no decision), ACCEPT recovery')
        endpoints = node.get_publishers_info_by_topic('/inspection/decision')
        assert len(endpoints) == 1
        assert endpoints[0].qos_profile.reliability == ReliabilityPolicy.RELIABLE
        assert endpoints[0].qos_profile.durability == DurabilityPolicy.VOLATILE
        output = stop(processes[0], signal.SIGINT)
        assert 'Measurement not classified' in output
    finally:
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=5)
        executor.shutdown(timeout_sec=2); node.destroy_node(); context.try_shutdown()


@pytest.mark.parametrize('sig', [signal.SIGINT, signal.SIGTERM])
def test_installed_signal(sig):
    executable = str(Path(get_package_prefix('inspection_ros')) / 'lib/inspection_ros/decision_node')
    process = subprocess.Popen([executable], cwd='/tmp', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        time.sleep(2)
        assert process.poll() is None
        stop(process, sig)
    finally:
        if process.poll() is None: process.kill(); process.communicate(timeout=5)


def test_installed_invalid_configuration():
    result = subprocess.run(['ros2', 'run', 'inspection_ros', 'decision_node', '--ros-args',
                             '-p', 'length_min_mm:=42.0'], cwd='/tmp',
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=15)
    assert result.returncode != 0
    assert 'invalid decision configuration' in result.stdout
    assert 'Traceback' not in result.stdout


def test_ros2_run_installed_from_outside_checkout():
    process = subprocess.Popen(['ros2', 'run', 'inspection_ros', 'decision_node'], cwd='/tmp',
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        time.sleep(2)
        assert process.poll() is None
        os.killpg(process.pid, signal.SIGINT)
        output, _ = process.communicate(timeout=10)
        assert process.returncode == 0, output
        assert 'Traceback' not in output
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)
