"""Installed ROS process checks; run after building and sourcing the overlay."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import numpy as np
import pytest
import rclpy
from ament_index_python.packages import get_package_prefix
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import Image

from vision_inspection import PlanarCalibration, measure_rectangle
from vision_inspection.synthetic import render_rectangle


def executable():
    return str(Path(get_package_prefix("inspection_ros")) / "lib/inspection_ros/synthetic_camera")


@contextmanager
def camera_process(command):
    process = subprocess.Popen(
        command, cwd="/tmp", stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, start_new_session=True,
    )
    try:
        yield process
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
        try:
            output, _ = process.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=3)
            pytest.fail("Camera process did not stop within 8 seconds")
        assert process.returncode == 0, output
        assert "Traceback" not in output, output
        # A launcher must reap its node too, not leave a process in its group.
        with pytest.raises(ProcessLookupError):
            os.killpg(process.pid, 0)


@pytest.fixture
def receiver():
    context = Context()
    rclpy.init(context=context, signal_handler_options=SignalHandlerOptions.NO)
    node = Node("synthetic_camera_test_receiver", context=context)
    executor = SingleThreadedExecutor(context=context)
    executor.add_node(node)
    images = []
    node.create_subscription(
        Image, "/inspection/image_raw", images.append,
        QoSProfile(
            history=HistoryPolicy.KEEP_LAST, depth=1,
            reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE,
        ),
    )
    yield node, images
    executor.shutdown(timeout_sec=2)
    node.destroy_node()
    context.try_shutdown()


def receive(node, images, process, count):
    deadline = time.monotonic() + 20
    while len(images) < count and time.monotonic() < deadline:
        assert process.poll() is None, process.communicate(timeout=1)[0]
        node.executor.spin_once(timeout_sec=min(0.2, max(0, deadline - time.monotonic())))
    assert len(images) >= count, "Timed out waiting for actual DDS images"


@pytest.mark.parametrize("rate", [None, 2.0])
def test_installed_ros2_run_images_qos_and_measurement(receiver, rate):
    node, images = receiver
    command = ["ros2", "run", "inspection_ros", "synthetic_camera"]
    if rate is not None:
        command += ["--ros-args", "-p", f"publish_rate_hz:={rate}"]
    with camera_process(command) as process:
        receive(node, images, process, 4)
        expected = render_rectangle(
            image_shape=(240, 320),
            plane_to_pixel=np.array([[4, 0, 160], [0, 4.5, 130], [0, 0, 1.0]]),
            center_mm=(0, 0), size_mm=(40, 20), angle_deg=23, samples_per_axis=8,
        ).tobytes(order="C")
        stamps = []
        for image in images:
            assert (image.height, image.width, image.step) == (240, 320, 320)
            assert (image.encoding, image.is_bigendian) == ("mono8", 0)
            assert image.header.frame_id == "inspection_camera_optical_frame"
            assert len(image.data) == 76800
            assert bytes(image.data) == expected
            stamp = image.header.stamp.sec * 10**9 + image.header.stamp.nanosec
            assert abs(node.get_clock().now().nanoseconds - stamp) < 5 * 10**9
            stamps.append(stamp)
        assert all(later > earlier > 0 for earlier, later in zip(stamps, stamps[1:]))
        endpoints = node.get_publishers_info_by_topic("/inspection/image_raw")
        assert len(endpoints) == 1
        qos = endpoints[0].qos_profile
        assert qos.reliability == ReliabilityPolicy.RELIABLE
        assert qos.durability == DurabilityPolicy.VOLATILE
        # Some Humble RMWs report UNKNOWN history/depth on discovered endpoints;
        # the node's explicit profile is checked separately below.
        assert endpoints[0].topic_type == "sensor_msgs/msg/Image"
        calibration = PlanarCalibration.from_correspondences(
            [[40, 40], [280, 40], [280, 220], [40, 220]],
            [[-30, -20], [30, -20], [30, 20], [-30, 20]],
        )
        image = np.frombuffer(bytes(images[0].data), dtype=np.uint8).reshape(240, 320)
        measured = measure_rectangle(image, calibration)
        assert measured.length_mm == pytest.approx(40.042, abs=0.001)
        assert measured.width_mm == pytest.approx(20.042, abs=0.001)
        print(json.dumps({
            "received": len(images), "stamps_ns": stamps,
            "length_mm": measured.length_mm, "width_mm": measured.width_mm,
            "launcher_pid": process.pid, "cwd": "/tmp",
            "publish_rate_hz": 1.0 if rate is None else rate,
        }))


@pytest.mark.parametrize("stop_signal", [signal.SIGINT, signal.SIGTERM])
def test_installed_entrypoint_signal_exit(receiver, stop_signal):
    node, images = receiver
    command = [executable()]
    if stop_signal == signal.SIGTERM:
        command += ["--ros-args", "-p", "publish_rate_hz:=2.0"]
    with camera_process(command) as process:
        receive(node, images, process, 2)
        process.send_signal(stop_signal)
        process.wait(timeout=5)
        print(f"{stop_signal.name}: installed node exited {process.returncode}; pid={process.pid}")


@pytest.mark.parametrize("value", [
    "0.0", "0.099999999", "10.000000001", ".nan", ".inf", "-.inf",
    "1", "true", "'1.0'",
])
def test_installed_entrypoint_rejects_invalid_rate(value):
    result = subprocess.run(
        [executable(), "--ros-args", "-p", f"publish_rate_hz:={value}"],
        cwd="/tmp", text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15,
    )
    assert result.returncode != 0, result.stdout
    assert "publish_rate_hz" in result.stdout, result.stdout
    assert "Traceback" not in result.stdout, result.stdout


def test_explicit_publisher_qos(receiver):
    from inspection_ros.synthetic_camera import SyntheticCamera

    node = SyntheticCamera(context=receiver[0].context)
    try:
        qos = node._publisher.qos_profile
        assert qos.history == HistoryPolicy.KEEP_LAST
        assert qos.depth == 1
        assert qos.reliability == ReliabilityPolicy.RELIABLE
        assert qos.durability == DurabilityPolicy.VOLATILE
    finally:
        node.destroy_node()
