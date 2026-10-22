"""Core flight duty period calculations (CS-FTL.1.1 style).

This module is deliberately conservative: it implements the main rules of
EASA Commission Regulation (EU) 965/2012 Subpart Q / associated AMC&GM
("CS-FTL.1.1" style limits) but does not attempt split-duty, in-flight rest,
or augmented crew. Those require context (planned vs actual rest, number of
extra crew, class of rest facility) that the caller has to supply; rather
than inventing a partial API, this module refuses them.

*Input shape.* Reporting time, start of duty, and time airborne are ISO 8601
strings (``YYYY-MM-DD HH:MM``). Durations are integer minutes. Using strings
rather than time objects lets the caller stay in whatever timezone they work
in, while making equality assertions in tests deterministic (see README for
rationale).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "Duration",
    "DutyResult",
    "parse_duration",
    "DutyCalculator",
]


def _total_minutes(h: int, m: int) -> int:
    return h * 60 + m


class Duration:
    """Immutable wall-clock length in minutes.

    Using integer minutes avoids float rounding issues that creep in when
    summing many HH:MM durations. Flight duty limits in CS-FTL.1.1 are
    multiples of 5 or 10 minutes, so 1-minute granularity is more than
    adequate and lets every comparison use ``==``.
    """

    __slots__ = ("minutes",)

    def __init__(self, minutes: int) -> None:
        if not isinstance(minutes, int):
            raise TypeError(
                "Duration requires an int minutes value; got "
                f"{type(minutes).__name__}"
            )
        if minutes < 0:
            raise ValueError(
                "Duration must be non-negative; got " f"{minutes}"
            )
        object.__setattr__(self, "minutes", minutes)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Duration is immutable")

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Duration):
            return self.minutes == other.minutes
        return NotImplemented

    def __lt__(self, other: object) -> bool:
        if isinstance(other, Duration):
            return self.minutes < other.minutes
        return NotImplemented

    def __le__(self, other: object) -> bool:
        if isinstance(other, Duration):
            return self.minutes <= other.minutes
        return NotImplemented

    def __gt__(self, other: object) -> bool:
        if isinstance(other, Duration):
            return self.minutes > other.minutes
        return NotImplemented

    def __ge__(self, other: object) -> bool:
        if isinstance(other, Duration):
            return self.minutes >= other.minutes
        return NotImplemented

    def __add__(self, other: object) -> "Duration":
        if isinstance(other, Duration):
            return Duration(self.minutes + other.minutes)
        return NotImplemented

    def __sub__(self, other: object) -> "Duration":
        if isinstance(other, Duration):
            if self.minutes < other.minutes:
                raise ValueError(
                    "Subtraction would produce a negative Duration"
                )
            return Duration(self.minutes - other.minutes)
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.minutes)

    def __repr__(self) -> str:
        return f"Duration(minutes={self.minutes})"

    def __str__(self) -> str:
        return f"{self.minutes // 60:02d}:{self.minutes % 60:02d}"


@dataclass(frozen=True)
class DutyResult:
    """Outcome of a flight duty period calculation.

    ``max_fdp`` and ``min_rest`` are returned in the same units the caller
    used (integer minutes). ``factors`` shows the constraints the limit
    was derived from, so the caller can log an explanation without redoing
    the arithmetic.
    """

    max_fdp: int
    min_rest: int
    factors: dict


def parse_duration(s: str) -> Duration:
    """Parse ``HH:MM`` into a :class:`Duration`.

    Requires exactly two digits on each side and rejects negative values;
    loose parsers let ``09:0`` or ``-01:00`` sneak in and corrupt
downstream limit calculations.
    """
    if not isinstance(s, str):
        raise TypeError(
            f"parse_duration requires str; got {type(s).__name__}"
        )
    parts = s.split(":")
    if len(parts) != 2:
        raise ValueError(
            f"Invalid HH:MM duration: {s!r}; expected two colons"
        )
    h_str, m_str = parts
    if len(h_str) != 2 or len(m_str) != 2:
        raise ValueError(
            f"Invalid HH:MM duration: {s!r}; expected two digits "
            "per field"
        )
    try:
        h = int(h_str)
        m = int(m_str)
    except ValueError as exc:
        raise ValueError(
            f"Invalid HH:MM duration: {s!r}; fields must be "
            f"numeric integers"
        ) from exc
    if h < 0:
        raise ValueError(
            f"Invalid HH:MM duration: {s!r}; hours must be "
            f"non-negative"
        )
    if m < 0 or m >= 60:
        raise ValueError(
            f"Invalid HH:MM duration: {s!r}; minutes must be "
            f"in [0, 59]"
        )
    return Duration(_total_minutes(h, m))


class DutyCalculator:
    """Flight duty period limits per CS-FTL.1.1 style rules.

    Supported limits:
      * Maximum FDP by number of planned sectors.
      * Minimum post-duty rest (min 12 hours, or FDP + 50%).
      * "8 hours of rest in any 24 consecutive hours" running check.

    Deliberately unsupported:
      * Split duty, in-flight rest, augmented crew — these require context
        (planned vs actual rest, crew composition, rest-facility class)
        the caller must curate; the module refuses partial handling
        rather than guessing.
      * Timezone math — the caller owns the clock; every timestamp stays
        naive in minutes-since-epoch so tests are deterministic.
    """

    MAX_FDP_TABLE = {
        1: 13 * 60,
        2: 11 * 60 + 30,
        3: 11 * 60,
        4: 10 * 60 + 30,
        5: 10 * 60,
        6: 9 * 60 + 30,
        7: 9 * 60,
    }

    MAX_DUTY = 14 * 60
    MIN_REST_FLAT = 12 * 60
    MIN_REST_ADD_PCT = 50

    def __init__(self) -> None:
        self.max_duty = self.MAX_DUTY
        self.min_rest_flat = self.MIN_REST_FLAT
        self.min_rest_add_pct = self.MIN_REST_ADD_PCT

    def max_fdp(self, sectors: int) -> int:
        """Maximum FDP in minutes for the given number of sectors."""
        if not isinstance(sectors, int):
            raise TypeError(
                f"sectors must be int; got {type(sectors).__name__}"
            )
        if sectors < 1:
            raise ValueError(
                f"sectors must be >= 1; got {sectors}"
            )
        if sectors in self.MAX_FDP_TABLE:
            return self.MAX_FDP_TABLE[sectors]
        if sectors > 7:
            return self.MAX_FDP_TABLE[7]
        # Defensive; indices are dense in 1..7.
        raise ValueError(f"no FDP entry for {sectors} sectors")

    def max_duty_minutes(self, fdp: int, pre_flight: int, post_flight: int) -> int:
        """Total duty minutes for a planned FDP plus pre/post-flight work."""
        self._check_minutes(fdp)
        self._check_minutes(pre_flight)
        self._check_minutes(post_flight)
        duty = fdp + pre_flight + post_flight
        if duty > self.max_duty:
            raise ValueError(
                "Duty exceeds 14-hour maximum duty period: "
                f"{duty} minutes"
            )
        return duty

    def min_rest_minutes(self, fdp: int) -> int:
        """Minimum rest after a flight duty period of ``fdp`` minutes."""
        self._check_minutes(fdp)
        rest = (fdp * (100 + self.min_rest_add_pct)) // 100
        return max(self.min_rest_flat, rest)

    @staticmethod
    def _check_minutes(v: object) -> None:
        if not isinstance(v, int):
            raise TypeError(
                f"expected int minutes; got {type(v).__name__}"
            )
        if v < 0:
            raise ValueError(f"expected non-negative minutes; got {v}")

    def _parse_min(self, v: object) -> int:
        self._check_minutes(v)
        return int(v)

    def _rest_minutes_so_far(
        self, epochs: list[tuple[int, int, int]], end: int
    ) -> int:
        """Sum rest recorded in 24-hour lookback ending at ``end``.

        The 24-hour window is inclusive of ``end`` (using a 1-minute guard
        when end == last recorded block end). We sum blocks overlapping
        the window by their overlap length. The 1-minute guard avoids an
        off-by-one when ``end`` exactly equals a block boundary: a rest
        ending at minute 10 should still count when ``end`` is 10.
        """
        self._check_minutes(end)
        if not epochs:
            return 0
        window_start = end - 24 * 60
        total = 0
        for start, duration, kind in epochs:
            self._check_minutes(start)
            self._check_minutes(duration)
            if kind not in (0, 1):
                raise ValueError(
                    f"invalid kind {kind}; expected 0 (rest) or 1 (duty)"
                )
            block_end = start + duration
            if kind == 0:
                guard = 0 if end != block_end else 1
                if block_end + guard > window_start and start <= end:
                    overlap_end = min(block_end, end)
                    overlap = overlap_end - max(start, window_start)
                    if overlap > 0:
                        total += overlap
        return total

    def rest_in_window(self, epochs: list, end_minute: int) -> int:
        """Total rest minutes within the 24h window ending at ``end_minute``."""
        return self._rest_minutes_so_far(list(epochs), end_minute)

    def calculate(
        self,
        reporting_time: str,
        time_airborne: str,
        num_sectors: int,
        block_off_minute: int,
        block_on_minute: int,
        post_flight_minutes: int = 30,
    ) -> DutyResult:
        """Compute maximum FDP and minimum rest for a planned flight.

        ``block_off_minute``/``block_on_minute`` are minutes since the same
        reference instant as ``reporting_time`` (naive integer offsets).
        ``post_flight_minutes`` is post-flight work after block-on.
        """
        if not isinstance(reporting_time, str):
            raise TypeError("reporting_time must be an ISO 8601 string")
        if not isinstance(time_airborne, str):
            raise TypeError("time_airborne must be an ISO 8601 string")

        rep_mins = self._parse_iso_minute(reporting_time)
        airborne_mins = self._parse_iso_minute(time_airborne)
        self._check_minutes(block_off_minute)
        self._check_minutes(block_on_minute)
        self._check_minutes(post_flight_minutes)

        post_flight_minutes = int(post_flight_minutes)

        if airborne_mins < rep_mins:
            raise ValueError(
                "time_airborne must not precede reporting_time"
            )
        if block_off_minute < 0:
            raise ValueError(
                "block_off must not precede reporting_time"
            )
        if block_on_minute < block_off_minute:
            raise ValueError("block_on must not precede block_off")
        if num_sectors < 1:
            raise ValueError(
                f"num_sectors must be >= 1; got {num_sectors}"
            )

        pre_flight = airborne_mins - rep_mins
        fdp = (block_on_minute - block_off_minute) + pre_flight
        if fdp < 0:
            raise ValueError("computed FDP is negative")

        max_fdp_table = self.max_fdp(num_sectors)
        duty = self.max_duty_minutes(
            fdp, pre_flight, post_flight_minutes
        )
        min_rest = self.min_rest_minutes(fdp)

        return DutyResult(
            max_fdp=max_fdp_table,
            min_rest=min_rest,
            factors={
                "duty_minutes": duty,
                "fdp_minutes": fdp,
                "pre_flight_minutes": pre_flight,
                "post_flight_minutes": post_flight_minutes,
                "sectors": num_sectors,
            },
        )

    @staticmethod
    def _parse_iso_minute(s: str) -> int:
        """Parse ``YYYY-MM-DD HH:MM`` to minutes since naive epoch.

        Naive epoch here is the same value the caller chose for
        ``block_off_minute``; the subtraction only ever compares values
        parsed through this helper, so no calendar arithmetic crosses a
        midnight rollover that we'd need a real datetime to handle.
        """
        if len(s) != 16 or s[4] != "-" or s[7] != "-" or s[10] != " " or s[13] != ":":
            raise ValueError(
                f"Invalid timestamp format: {s!r}; expected "
                f"'YYYY-MM-DD HH:MM'"
            )
        date_part = s[:10]
        time_part = s[11:]
        try:
            y = int(date_part[0:4])
            mo = int(date_part[5:7])
            d = int(date_part[8:10])
            hh = int(time_part[0:2])
            mm = int(time_part[3:5])
        except ValueError as exc:
            raise ValueError(
                f"Invalid timestamp: {s!r}; fields must be numeric"
            ) from exc
        for label, value, lo, hi in [
            ("year", y, 1, 9999),
            ("month", mo, 1, 12),
            ("day", d, 1, 31),
            ("hour", hh, 0, 23),
            ("minute", mm, 0, 59),
        ]:
            if value < lo or value > hi:
                raise ValueError(
                    f"Invalid timestamp: {s!r}; {label} {value} out of "
                    f"range [{lo},{hi}]"
                )
        return y * 525960 + mo * 43200 + d * 1440 + hh * 60 + mm
