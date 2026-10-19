from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RollingWindow:
    calib_start: int
    calib_end: int
    test_start: int
    test_end: int


def rolling_windows(
    total_days: int,
    calib_days: int = 250,
    test_days: int = 60,
    step: int = 60,
) -> list[RollingWindow]:
    """Build rolling walk-forward windows without overlapping calibration and test."""
    if calib_days <= 0 or test_days <= 0 or step <= 0:
        raise ValueError("calib_days, test_days and step must be positive")
    windows: list[RollingWindow] = []
    start = 0
    while start + calib_days + test_days <= total_days:
        calib_start = start
        calib_end = start + calib_days
        test_start = calib_end
        test_end = test_start + test_days
        windows.append(RollingWindow(calib_start, calib_end, test_start, test_end))
        start += step
    return windows
