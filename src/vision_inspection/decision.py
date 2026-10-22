"""ROS-independent dimensional decisions using configured millimeter guards."""

from enum import Enum
from fractions import Fraction
from math import inf, isfinite
from numbers import Rational, Real

from .measurement import RectangleMeasurement


class InspectionDecision(Enum):
    """Conformity of the guarded dimensions to their closed tolerances."""

    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    REVIEW = "REVIEW"


def _check_real(value, name, *, positive):
    # Compare in the original numeric type: float conversion can erase a tiny
    # negative guard, a positive dimension, or the ordering of two close values.
    if (not isinstance(value, Real) or isinstance(value, bool)
            or not -inf < value < inf
            or (value <= 0 if positive else value < 0)):
        domain = "positive" if positive else "nonnegative"
        raise ValueError(f"{name} must be a finite {domain} real scalar, not bool")


def _as_float(value, name, *, positive):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be representable as a finite float") from error
    _check_real(result, name, positive=positive)
    return result


def _comparison_value(value):
    # Exact ratios avoid NumPy coercing a huge integer to float, rounding a
    # Fraction, or rejecting a comparison between Fraction and longdouble.
    if isinstance(value, Rational):
        return Fraction(int(value.numerator), int(value.denominator))
    if hasattr(value, "as_integer_ratio"):
        return Fraction(*value.as_integer_ratio())
    return value


def _positive_pair(lower, upper, lower_name, upper_name):
    _check_real(lower, lower_name, positive=True)
    _check_real(upper, upper_name, positive=True)
    try:
        reversed_order = _comparison_value(lower) > _comparison_value(upper)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{lower_name} and {upper_name} must be ordered reals") from error
    if reversed_order:
        raise ValueError(f"{lower_name} must not exceed {upper_name}")
    converted_lower = _as_float(lower, lower_name, positive=True)
    converted_upper = _as_float(upper, upper_name, positive=True)
    if converted_lower > converted_upper:
        raise ValueError(f"{lower_name} must not exceed {upper_name} after conversion")
    return converted_lower, converted_upper


def _limits(value, name):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError(f"{name} must be a two-element tuple or list")
    return _positive_pair(value[0], value[1], f"{name}[0]", f"{name}[1]")


def _guard(value, name):
    _check_real(value, name, positive=False)
    return _as_float(value, name, positive=False)


def _interval(value, guard, name):
    lower, upper = value - guard, value + guard
    if not isfinite(lower) or not isfinite(upper):
        raise ValueError(f"{name} guarded interval must have finite endpoints")
    return lower, upper


def classify_measurement(
    measurement,
    length_limits_mm,
    width_limits_mm,
    *,
    length_guard_mm=0.0,
    width_guard_mm=0.0,
) -> InspectionDecision:
    """Classify a RectangleMeasurement without changing any input.

    Sides must be finite positive real scalars, length >= width. Each tolerance
    is a two-element tuple or list of finite positive reals, lower <= upper.
    Guards are finite nonnegative reals in millimeters; bool is never accepted.
    Sign, finiteness and ordering are checked before and after float conversion.
    Positive sides and tolerance endpoints must not underflow to zero.

    Each dimension represents [value - guard, value + guard]. ACCEPT requires
    both intervals inside their closed tolerances. REJECT requires at least one
    disjoint interval. All other valid cases, including external contact, yield
    REVIEW. Comparisons use no epsilon. Zero guards accept tolerance endpoints.

    Invalid data, float conversion overflow and nonfinite interval endpoints
    raise ValueError before any decision. Guards are configured assumptions,
    not calibrated uncertainties or confidence intervals. Corners are unused;
    this function does not certify geometry or physical measurement accuracy.
    """
    if not isinstance(measurement, RectangleMeasurement):
        raise ValueError("measurement must be a RectangleMeasurement")
    width, length = _positive_pair(
        measurement.width_mm, measurement.length_mm,
        "measurement.width_mm", "measurement.length_mm",
    )
    length_limits = _limits(length_limits_mm, "length_limits_mm")
    width_limits = _limits(width_limits_mm, "width_limits_mm")
    length_guard = _guard(length_guard_mm, "length_guard_mm")
    width_guard = _guard(width_guard_mm, "width_guard_mm")
    intervals = (
        _interval(length, length_guard, "length_mm"),
        _interval(width, width_guard, "width_mm"),
    )
    tolerances = (length_limits, width_limits)

    if any(upper < low or lower > high
           for (lower, upper), (low, high) in zip(intervals, tolerances)):
        return InspectionDecision.REJECT
    if all(low <= lower and upper <= high
           for (lower, upper), (low, high) in zip(intervals, tolerances)):
        return InspectionDecision.ACCEPT
    return InspectionDecision.REVIEW
