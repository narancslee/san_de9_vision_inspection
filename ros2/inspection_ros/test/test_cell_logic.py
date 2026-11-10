"""Decision freshness and state transitions for the simulated cell."""

import pytest

from inspection_ros.cell_logic import CellLogic


@pytest.mark.parametrize("code", [1, 2, 3])
def test_valid_states(code):
    cell = CellLogic(3.0)
    cell.update(code, 40., 20., 10_000_000_000, 10_000_000_000, 5., "source")
    assert (cell.state, cell.reason, cell.header) == (code, "fresh", "source")


@pytest.mark.parametrize("code,length,width,stamp,now", [
    (0, 40., 20., 10_000_000_000, 10_000_000_000),
    (1, float("nan"), 20., 10_000_000_000, 10_000_000_000),
    (1, 10., 20., 10_000_000_000, 10_000_000_000),
    (1, 40., 20., 0, 10_000_000_000),
    (1, 40., 20., 6_000_000_000, 10_000_000_000),
    (1, 40., 20., 11_000_000_000, 10_000_000_000),
])
def test_invalid_is_unavailable_then_recovers(code, length, width, stamp, now):
    cell = CellLogic(3.0)
    cell.update(code, length, width, stamp, now, 5., "bad")
    assert (cell.state, cell.reason, cell.header) == (0, "invalid", None)
    cell.update(1, 40., 20., 10_000_000_000, 10_000_000_000, 6., "good")
    assert (cell.state, cell.reason) == (1, "fresh")


def test_duplicate_cannot_refresh_and_valid_new_stamp_recovers():
    cell = CellLogic(3.)
    cell.update(1, 40., 20., 10_000_000_000, 10_000_000_000, 5., "one")
    cell.update(1, 40., 20., 10_000_000_000, 10_000_000_000, 6., "duplicate")
    assert (cell.state, cell.reason) == (0, "invalid")
    cell.update(2, 40., 20., 10_100_000_000, 10_100_000_000, 6., "two")
    assert (cell.state, cell.reason) == (2, "fresh")


def test_wall_timeout_even_if_ros_clock_pauses():
    cell = CellLogic(3.)
    cell.update(1, 40., 20., 10_000_000_000, 10_000_000_000, 5., "one")
    cell.expire(10_000_000_000, 8.01)
    assert (cell.state, cell.reason, cell.header) == (0, "stale", None)


@pytest.mark.parametrize("timeout", [0., -1., float("nan"), float("inf"), True, "3"])
def test_invalid_timeout(timeout):
    with pytest.raises(ValueError):
        CellLogic(timeout)
