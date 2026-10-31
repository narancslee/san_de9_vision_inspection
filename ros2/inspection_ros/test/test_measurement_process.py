"""Exercise installed nodes in separate processes over DDS."""
import os
from pathlib import Path
import signal
import subprocess
import time

import pytest
import rclpy
from ament_index_python.packages import get_package_prefix, get_package_share_directory
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import Image
from inspection_interfaces.msg import RectangleMeasurement
from inspection_ros.synthetic_camera import fixture_image, pack_image


def executable(name):
    return str(Path(get_package_prefix('inspection_ros')) / 'lib/inspection_ros' / name)


def spin_until(executor, predicate, timeout=20):
    end = time.monotonic() + timeout
    while not predicate() and time.monotonic() < end:
        executor.spin_once(timeout_sec=0.1)
    assert predicate(), 'DDS timeout'


def stop(process, sig):
    process.send_signal(sig)
    output, _ = process.communicate(timeout=8)
    assert process.returncode == 0, output
    assert 'Traceback' not in output, output
    return output


def test_three_processes_invalid_image_and_recovery():
    context = Context()
    rclpy.init(context=context, signal_handler_options=SignalHandlerOptions.NO)
    node = Node('measurement_process_test', context=context)
    executor = SingleThreadedExecutor(context=context)
    executor.add_node(node)
    images, results = [], []
    qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE)
    node.create_subscription(Image, '/inspection/image_raw', images.append, qos)
    node.create_subscription(RectangleMeasurement, '/inspection/rectangle_measurement', results.append, qos)
    publisher = node.create_publisher(Image, '/inspection/image_raw', qos)
    config = str(Path(get_package_share_directory('inspection_ros')) / 'config/synthetic_calibration.yaml')
    env = os.environ.copy()  # Child nodes use the test process's ROS domain.
    processes = []
    try:
        meter = subprocess.Popen([executable('measurement_node'), '--ros-args', '--params-file', config], cwd='/tmp', env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        processes.append(meter)
        camera = subprocess.Popen([executable('synthetic_camera'), '--ros-args', '-p', 'publish_rate_hz:=2.0'], cwd='/tmp', env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        processes.append(camera)
        spin_until(executor, lambda: len(results) >= 2 and len(images) >= 2)
        assert meter.poll() is None and camera.poll() is None
        matching = [(i, o) for i in images for o in results if i.header == o.header]
        assert matching
        for i, o in matching:
            assert i.header.frame_id == 'inspection_camera_optical_frame'
            assert i.header.stamp.sec > 0
            assert o.length_mm == pytest.approx(40.042, abs=.001)
            assert o.width_mm == pytest.approx(20.042, abs=.001)
        print(f'matched image/result headers: {len(matching)}; dimensions {matching[0][1].length_mm:.6f} x {matching[0][1].width_mm:.6f} mm')
        stop(camera, signal.SIGINT)
        # Drain in-flight frames before injecting uniquely stamped messages.
        end = time.monotonic() + 1
        while time.monotonic() < end: executor.spin_once(timeout_sec=.1)
        bad = pack_image(fixture_image()); bad.header.stamp.sec = 101; bad.encoding = 'rgb8'
        good = pack_image(fixture_image()); good.header.stamp.sec = 102
        spin_until(executor, lambda: publisher.get_subscription_count() >= 1)
        publisher.publish(bad)
        end = time.monotonic() + 1
        while time.monotonic() < end: executor.spin_once(timeout_sec=.1)
        publisher.publish(good)
        spin_until(executor, lambda: any(x.header.stamp.sec == 102 for x in results))
        assert not any(x.header.stamp.sec == 101 for x in results)
        print('invalid encoding produced no result; subsequent valid image produced a result')
        output = stop(meter, signal.SIGTERM)
        assert 'expected mono8' in output
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill(); process.communicate(timeout=5)
        executor.shutdown(timeout_sec=2); node.destroy_node(); context.try_shutdown()


@pytest.mark.parametrize('sig', [signal.SIGINT, signal.SIGTERM])
def test_installed_measurement_signal(sig):
    process = subprocess.Popen([executable('measurement_node')], cwd='/tmp', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        time.sleep(2)
        assert process.poll() is None
        stop(process, sig)
        print(f'{sig.name}: measurement node exited 0')
    finally:
        if process.poll() is None: process.kill(); process.communicate(timeout=5)


def test_installed_invalid_calibration():
    result = subprocess.run([executable('measurement_node'), '--ros-args', '-p', 'frame_id:=""'], cwd='/tmp', text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15)
    assert result.returncode != 0
    assert 'frame_id' in result.stdout
    assert 'Traceback' not in result.stdout
