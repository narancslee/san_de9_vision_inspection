"""Freshness-gated state for a simulated inspection cell."""

import math


class CellLogic:
    """Track frame-level decisions; no physical part IDs or control output."""

    def __init__(self, timeout):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ValueError("timeout_seconds must be finite and positive")
        self.timeout = float(timeout)
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        self.state = 0
        self.reason = "waiting"
        self.last_stamp = None
        self.last_receipt = None
        self.header = None

    def update(self, code, length, width, stamp, now, wall, header):
        valid = (type(code) is int and code in (1, 2, 3)
                 and math.isfinite(length) and math.isfinite(width)
                 and length >= width > 0
                 and type(stamp) is int and stamp > 0
                 and type(now) is int and now > 0
                 and math.isfinite(wall)
                 and 0 <= (now - stamp) * 1e-9 <= self.timeout
                 and (self.last_stamp is None or stamp > self.last_stamp))
        if not valid:
            self.state, self.reason = 0, "invalid"
            self.header = None
            self.last_receipt = None
            return
        self.state, self.reason = code, "fresh"
        self.last_stamp, self.last_receipt, self.header = stamp, wall, header

    def expire(self, now, wall):
        if self.state and (self.last_receipt is None or wall < self.last_receipt
                           or wall - self.last_receipt > self.timeout
                           or now <= 0 or now < self.last_stamp
                           or (now - self.last_stamp) * 1e-9 > self.timeout):
            self.state, self.reason = 0, "stale"
            self.header = None
            self.last_receipt = None
