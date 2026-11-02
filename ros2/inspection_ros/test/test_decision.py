"""ROS decision adapter and startup configuration contracts."""
from unittest.mock import Mock, patch

import pytest
import rclpy
from rclpy.context import Context
from rclpy.parameter import Parameter
from rclpy.signals import SignalHandlerOptions

from inspection_interfaces.msg import InspectionDecision, RectangleMeasurement
from inspection_ros import decision_node


@pytest.fixture
def node():
    context = Context()
    rclpy.init(context=context, signal_handler_options=SignalHandlerOptions.NO)
    node = decision_node.DecisionNode(context=context)
    node._publisher = Mock()
    yield node
    node.destroy_node()
    context.try_shutdown()


def measurement(length, width, stamp=42):
    msg = RectangleMeasurement(length_mm=length, width_mm=width)
    msg.header.frame_id = 'source'
    msg.header.stamp.sec = stamp
    msg.header.stamp.nanosec = 987
    return msg


@pytest.mark.parametrize('length,width,code', [
    (40., 20., InspectionDecision.ACCEPT),
    (39., 20., InspectionDecision.REVIEW),
    (42., 20., InspectionDecision.REJECT),
])
def test_adapter_decisions_and_fields(node, length, width, code):
    msg = measurement(length, width)
    node._on_measurement(msg)
    result = node._publisher.publish.call_args.args[0]
    assert (result.header, result.length_mm, result.width_mm, result.decision) == (
        msg.header, length, width, code)


@pytest.mark.parametrize('name,value', [
    ('length_min_mm', 0.), ('length_max_mm', 38.),
    ('width_min_mm', -1.), ('width_max_mm', 18.),
    ('length_guard_mm', -0.1), ('width_guard_mm', float('nan')),
    ('length_max_mm', float('inf')),
])
def test_bad_config(node, name, value):
    with pytest.raises(decision_node.ConfigurationError, match='invalid decision configuration'):
        decision_node.DecisionNode(context=node.context, parameter_overrides=[Parameter(name, value=value)])


def test_read_only(node):
    assert not node.set_parameters([Parameter('length_min_mm', value=10.)])[0].successful


@pytest.mark.parametrize('length,width', [(float('nan'), 20.), (40., float('inf')),
                                          (0., 20.), (10., 20.), (-1., 1.)])
def test_bad_measurement_then_recovery(node, length, width):
    node._on_measurement(measurement(length, width, 100))
    node._publisher.publish.assert_not_called()
    node._on_measurement(measurement(40., 20., 101))
    node._publisher.publish.assert_called_once()
    assert node._publisher.publish.call_args.args[0].header.stamp.sec == 101


def test_unknown_result_does_not_publish(node):
    with patch.object(node, '_classify', return_value='ACCEPT'):
        node._on_measurement(measurement(40., 20.))
    node._publisher.publish.assert_not_called()


def test_configured_limits_and_guards_change_result(node):
    configured = decision_node.DecisionNode(context=node.context, parameter_overrides=[
        Parameter('length_min_mm', value=35.), Parameter('length_max_mm', value=45.),
        Parameter('width_min_mm', value=15.), Parameter('width_max_mm', value=25.),
        Parameter('length_guard_mm', value=2.), Parameter('width_guard_mm', value=2.),
    ])
    configured._publisher = Mock()
    try:
        configured._on_measurement(measurement(39., 20.))
        assert configured._publisher.publish.call_args.args[0].decision == InspectionDecision.ACCEPT
        configured._on_measurement(measurement(35., 20.))
        assert configured._publisher.publish.call_args.args[0].decision == InspectionDecision.REVIEW
    finally:
        configured.destroy_node()


def test_explicit_qos(node):
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, ReliabilityPolicy
    # The fixture replaces the publisher; inspect a fresh node's endpoints.
    actual = decision_node.DecisionNode(context=node.context)
    try:
        for endpoint in (actual._publisher, actual._subscription):
            qos = endpoint.qos_profile
            assert qos.history == HistoryPolicy.KEEP_LAST
            assert qos.depth == 1
            assert qos.reliability == ReliabilityPolicy.RELIABLE
            assert qos.durability == DurabilityPolicy.VOLATILE
    finally:
        actual.destroy_node()
