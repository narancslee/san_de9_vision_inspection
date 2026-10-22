"""Hand-derived interval decisions, numeric validation and input preservation."""

from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
from math import inf, nextafter

import numpy as np
import pytest

from vision_inspection import (
    InspectionDecision,
    PlanarCalibration,
    RectangleMeasurement,
    classify_measurement,
    measure_rectangle,
)


ACCEPT = InspectionDecision.ACCEPT
REJECT = InspectionDecision.REJECT
REVIEW = InspectionDecision.REVIEW
LENGTH_LIMITS = (39, 41)
WIDTH_LIMITS = (19, 21)
TINY = Fraction(1, 10**400)
CORNERS = ((-20, -10), (20, -10), (20, 10), (-20, 10))


def measurement(length=40, width=20):
    return RectangleMeasurement(length, width, CORNERS)


@pytest.mark.parametrize("length,width,expected", [
    (40, 20, ACCEPT), (40, 19, REVIEW), (40, 18, REJECT),
    (39, 20, REVIEW), (39, 19, REVIEW), (39, 18, REJECT),
    (38, 20, REJECT), (38, 19, REJECT), (38, 18, REJECT),
])
def test_all_interval_state_combinations(length, width, expected):
    # With 0.5 guards: 40/20 are inside, 39/19 overlap, 38/18 are disjoint.
    assert classify_measurement(
        measurement(length, width), LENGTH_LIMITS, WIDTH_LIMITS,
        length_guard_mm=0.5, width_guard_mm=0.5,
    ) is expected


@pytest.mark.parametrize("length,width,lg,wg,expected", [
    (39, 19, 0, 0, ACCEPT), (41, 21, 0, 0, ACCEPT),
    (38.5, 20, 0.5, 0, REVIEW), (41.5, 20, 0.5, 0, REVIEW),
    (40, 18.5, 0, 0.5, REVIEW), (40, 21.5, 0, 0.5, REVIEW),
    (38, 20, 0.5, 0, REJECT), (42, 20, 0.5, 0, REJECT),
    (40, 18, 0, 0.5, REJECT), (40, 22, 0, 0.5, REJECT),
    (40, 20, 1, 1, ACCEPT), (40, 20, 2, 0, REVIEW),
    (40, 20, 0, 2, REVIEW), (40, 20, 0.5, 2, REVIEW),
    (40, 20, 2, 0.5, REVIEW),
    (40, 20, 50, 0, REVIEW),  # Negative interval lower endpoint is valid.
])
def test_closed_boundaries_and_independent_guards(length, width, lg, wg, expected):
    assert classify_measurement(
        measurement(length, width), LENGTH_LIMITS, WIDTH_LIMITS,
        length_guard_mm=lg, width_guard_mm=wg,
    ) is expected


@pytest.mark.parametrize("field,boundary,direction,expected", [
    ("length", 39.0, -inf, REJECT), ("length", 39.0, inf, ACCEPT),
    ("length", 41.0, -inf, ACCEPT), ("length", 41.0, inf, REJECT),
    ("width", 19.0, -inf, REJECT), ("width", 19.0, inf, ACCEPT),
    ("width", 21.0, -inf, ACCEPT), ("width", 21.0, inf, REJECT),
])
def test_no_comparison_epsilon(field, boundary, direction, expected):
    sides = {field: nextafter(boundary, direction)}
    assert classify_measurement(measurement(**sides), LENGTH_LIMITS, WIDTH_LIMITS) is expected


@pytest.mark.parametrize("guard,expected", [(0, ACCEPT), (0.5, REVIEW)])
def test_single_point_tolerances(guard, expected):
    assert classify_measurement(
        measurement(), (40, 40), (20, 20),
        length_guard_mm=guard, width_guard_mm=guard,
    ) is expected


def test_square_and_guards_larger_than_sides():
    square = measurement(2, 2)
    assert classify_measurement(square, (1, 3), (1, 3)) is ACCEPT
    # A guard larger than the side is valid and produces a negative lower end.
    assert classify_measurement(
        square, (0.5, 6), (0.5, 6), length_guard_mm=3, width_guard_mm=3,
    ) is REVIEW


@pytest.mark.parametrize("scalar", [int, float, np.int64, np.float32, np.float64, Fraction])
def test_supported_real_scalars_and_list_limits(scalar):
    result = measurement(scalar(40), scalar(20))
    assert classify_measurement(
        result, [scalar(39), scalar(41)], [scalar(19), scalar(21)],
        length_guard_mm=scalar(1), width_guard_mm=scalar(1),
    ) is ACCEPT


def test_mixed_numpy_and_fraction_scalars():
    assert classify_measurement(
        measurement(Fraction(40), np.longdouble(20)),
        (np.float32(39), Fraction(41)), (Fraction(19), np.longdouble(21)),
        length_guard_mm=Fraction(1), width_guard_mm=np.int64(1),
    ) is ACCEPT


@pytest.mark.parametrize("lower,upper", [
    (np.float64(1), 1 - TINY), (1 + TINY, np.float64(1)),
    (np.longdouble(1), 1 - TINY), (1 + TINY, np.longdouble(1)),
])
def test_mixed_types_do_not_hide_reversed_original_order(lower, upper):
    with pytest.raises(ValueError, match="must not exceed"):
        classify_measurement(measurement(), (lower, upper), WIDTH_LIMITS)


@pytest.mark.parametrize("width", [np.float64(20), np.longdouble(20), Fraction(20)])
def test_huge_integer_with_mixed_side_types_raises_value_error(width):
    with pytest.raises(ValueError, match="measurement.length_mm"):
        classify_measurement(measurement(10**400, width), LENGTH_LIMITS, WIDTH_LIMITS)


def test_default_guards_match_explicit_zero():
    for length in (38, 39, 40, 41, 42):
        result = measurement(length)
        assert classify_measurement(result, LENGTH_LIMITS, WIDTH_LIMITS) is classify_measurement(
            result, LENGTH_LIMITS, WIDTH_LIMITS, length_guard_mm=0.0, width_guard_mm=-0.0,
        )
    # Positive guards may round to zero; positive dimensions and limits may not.
    assert classify_measurement(
        measurement(), LENGTH_LIMITS, WIDTH_LIMITS, length_guard_mm=TINY,
    ) is ACCEPT


BAD_SCALARS = [None, "20", 1j, [], [20], np.array(20.0), Decimal("20"),
               True, False, np.bool_(True), float("nan"), inf, -inf]


@pytest.mark.parametrize("value", BAD_SCALARS + [0, -1, TINY, 10**400])
@pytest.mark.parametrize("field", ["length", "width"])
def test_invalid_dimensions(field, value):
    with pytest.raises(ValueError, match="measurement"):
        classify_measurement(measurement(**{field: value}), LENGTH_LIMITS, WIDTH_LIMITS)


@pytest.mark.parametrize("value", [None, {}, (40, 20), object()])
def test_invalid_measurement_type(value):
    with pytest.raises(ValueError, match="measurement"):
        classify_measurement(value, LENGTH_LIMITS, WIDTH_LIMITS)


@pytest.mark.parametrize("length,width", [(19, 20), (1, 1 + TINY)])
def test_reversed_sides_before_conversion(length, width):
    with pytest.raises(ValueError, match="must not exceed"):
        classify_measurement(measurement(length, width), LENGTH_LIMITS, WIDTH_LIMITS)


@pytest.mark.parametrize("limits", [None, 20, "19,21", {19, 21}, {0: 19, 1: 21},
                                    np.array([19, 21]), (), (19,), (19, 20, 21)])
@pytest.mark.parametrize("field", ["length_limits_mm", "width_limits_mm"])
def test_invalid_limit_containers(field, limits):
    options = dict(length_limits_mm=LENGTH_LIMITS, width_limits_mm=WIDTH_LIMITS)
    options[field] = limits
    with pytest.raises(ValueError, match=field):
        classify_measurement(measurement(), **options)


@pytest.mark.parametrize("value", BAD_SCALARS + [0, -1, TINY, 10**400])
@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("field", ["length_limits_mm", "width_limits_mm"])
def test_invalid_limit_endpoints(field, index, value):
    limits = [19, 41]
    limits[index] = value
    options = dict(length_limits_mm=LENGTH_LIMITS, width_limits_mm=WIDTH_LIMITS)
    options[field] = limits
    with pytest.raises(ValueError, match=field):
        classify_measurement(measurement(), **options)


@pytest.mark.parametrize("limits", [(41, 39), (1 + TINY, 1)])
@pytest.mark.parametrize("field", ["length_limits_mm", "width_limits_mm"])
def test_reversed_limits_before_conversion(field, limits):
    options = dict(length_limits_mm=LENGTH_LIMITS, width_limits_mm=WIDTH_LIMITS)
    options[field] = limits
    with pytest.raises(ValueError, match="must not exceed"):
        classify_measurement(measurement(), **options)


@pytest.mark.parametrize("value", BAD_SCALARS + [-1, -TINY, 10**400])
@pytest.mark.parametrize("field", ["length_guard_mm", "width_guard_mm"])
def test_invalid_guards(field, value):
    with pytest.raises(ValueError, match=field):
        classify_measurement(measurement(), LENGTH_LIMITS, WIDTH_LIMITS, **{field: value})


class ConvertedFloat(float):
    """A Real whose float conversion differs from its original comparison value."""

    def __new__(cls, original, converted):
        instance = super().__new__(cls, original)
        instance.converted = converted
        return instance

    def __float__(self):
        return self.converted


@pytest.mark.parametrize("target,original,converted", [
    ("side", 40, 0.0), ("side", 40, inf), ("side", 40, float("nan")),
    ("side", 40, 19.0),  # Valid original ordering becomes length < width.
    ("limit", 39, 0.0), ("limit", 39, -1.0), ("limit", 39, inf),
    ("limit", 39, 42.0),  # Valid original limits become reversed.
    ("guard", 1, -1.0), ("guard", 1, inf), ("guard", 1, float("nan")),
])
def test_values_and_order_are_rechecked_after_conversion(target, original, converted):
    value = ConvertedFloat(original, converted)
    result = measurement(value) if target == "side" else measurement()
    limits = (value, 41) if target == "limit" else LENGTH_LIMITS
    options = {"length_guard_mm": value} if target == "guard" else {}
    with pytest.raises(ValueError):
        classify_measurement(result, limits, WIDTH_LIMITS, **options)


@pytest.mark.parametrize("field", ["length_guard_mm", "width_guard_mm"])
def test_finite_inputs_with_overflowing_interval(field):
    with pytest.raises(ValueError, match="finite endpoints"):
        classify_measurement(
            measurement(1e308, 1e308), (1e307, 1e308), (1e307, 1e308),
            **{field: 1e308},
        )


@pytest.mark.parametrize("overrides", [
    {"width_limits_mm": (21, 19)}, {"width_guard_mm": -1},
    {"length_guard_mm": -TINY}, {"width_guard_mm": inf},
])
def test_invalid_input_is_not_hidden_by_reject(overrides):
    options = dict(length_limits_mm=LENGTH_LIMITS, width_limits_mm=WIDTH_LIMITS)
    options.update(overrides)
    with pytest.raises(ValueError):
        classify_measurement(measurement(38, 20), **options)


def test_interval_overflow_is_not_hidden_by_reject():
    with pytest.raises(ValueError, match="width_mm"):
        classify_measurement(
            measurement(1e308, 1e308), LENGTH_LIMITS, WIDTH_LIMITS,
            width_guard_mm=1e308,
        )


@pytest.mark.parametrize("length,guard,expected", [
    (40, 0, ACCEPT), (40, 2, REVIEW), (38, 0, REJECT), (40, -1, None),
])
def test_inputs_are_unchanged(length, guard, expected):
    result = measurement(length)
    length_limits, width_limits = [39, 41], [19, 21]
    before = deepcopy((result, length_limits, width_limits))
    corners = result.corners_mm
    if expected is None:
        with pytest.raises(ValueError):
            classify_measurement(result, length_limits, width_limits, length_guard_mm=guard)
    else:
        assert classify_measurement(
            result, length_limits, width_limits, length_guard_mm=guard,
        ) is expected
    assert (result, length_limits, width_limits) == before
    assert result.corners_mm is corners


def test_corners_are_unused():
    result = RectangleMeasurement(40, 20, object())
    assert classify_measurement(result, LENGTH_LIMITS, WIDTH_LIMITS) is ACCEPT


def test_measured_image_to_public_decision_api():
    image = np.zeros((60, 100), np.uint8)
    image[15:35, 20:60] = 255
    result = measure_rectangle(image, PlanarCalibration(np.diag([0.25, 0.25, 1])))
    assert classify_measurement(
        result, (9.5, 10.5), (4.5, 5.5), length_guard_mm=0.25, width_guard_mm=0.25,
    ) is ACCEPT
    assert {member.value for member in InspectionDecision} == {"ACCEPT", "REJECT", "REVIEW"}
