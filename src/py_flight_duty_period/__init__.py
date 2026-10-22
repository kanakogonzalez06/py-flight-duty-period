# py_flight_duty_period
# Zero third-party dependencies; standard library only.

from .core import (
    Duration,
    DutyCalculator,
    DutyResult,
    parse_duration,
)

__all__ = [
    "Duration",
    "DutyCalculator",
    "DutyResult",
    "parse_duration",
]

__version__ = "0.1.0"
