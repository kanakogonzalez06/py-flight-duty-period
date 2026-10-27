# py_flight_duty_period

Calculates flight crew duty periods and minimum rest per CS-FTL.1.1 style limits (EASA Commission Regulation (EU) 965/2012 Subpart Q), with zero third-party dependencies.

## Usage

```python
from py_flight_duty_period import DutyCalculator, parse_duration, Duration, DutyResult

calc = DutyCalculator()

# Maximum FDP for a 3-sector day (minutes)
max_fdp = calc.max_fdp(3)  # 660

# Minimum rest after a 15-hour FDP (minutes)
min_rest = calc.min_rest_minutes(15 * 60)  # 1350

# Full duty calculation for a planned flight
result = calc.calculate(
    reporting_time="2024-01-15 06:00",
    time_airborne="2024-01-15 06:30",
    num_sectors=1,
    block_off_minute=6 * 60,
    block_on_minute=7 * 60 + 30,
    post_flight_minutes=30,
)
# result is a DutyResult(max_fdp=780, min_rest=720,
#                       factors={...})

# Duration strings are strict: exactly two digits per field
parse_duration("02:10") == Duration(130)
```

## Why this exists

A common need in operations tooling is to sanity-check a planned roster against the regulation's hard limits: maximum flight duty period by number of sectors, the 14-hour maximum duty period, and the minimum rest that must follow a given FDP. Doing this inline in spreadsheets or shell scripts is error-prone because the rules are tabular and integer-minute based.

This library encodes that one decision tree in plain Python. The trade-off: it deliberately handles only the *unexceptional* case. Split duty, in-flight rest, and augmented crew all depend on context this library refuses to guess (planned vs actual rest, number of extra crew, class of rest facility). Rather than expose a partial API, `DutyCalculator.calculate` raises `ValueError` if the caller asks for those — the caller has to assemble the inputs and curate the context.

## Inputs

Timestamps (`reporting_time`, `time_airborne`) are ISO 8601 strings of the form `YYYY-MM-DD HH:MM`. `block_off_minute` and `block_on_minute` are integer minutes since the same reference instant as `reporting_time`; both must be consistent with the ISO timestamp (e.g. if reporting is `06:00` and block-off is at minute 360, they agree). Timezone math is the caller's problem — every timestamp stays naive so tests are deterministic.

## Edge cases you will hit

- `parse_duration("2:10")` raises `ValueError`. The parser requires exactly two digits per field. This is intentional: flight ops times are zero-padded and loose parsing invites silent corruption downstream.
- `Duration(1.5)` raises `TypeError`. `Duration` is integer-minute only; float comparisons break determinism.
- `max_duty_minutes` raises `ValueError` if the composed duty exceeds 14 hours. There is no warning channel; it's pass or raise.
- `min_rest_minutes` uses `max(12 hours, FDP × 1.5)`. For FDPs below 8 hours this means the flat minimum dominates; for longer FDPs the 1.5× rule wins. This matches the CS-FTL rule, but callers sometimes expect the percentage to always apply.
- `max_fdp(8)` returns the cap for 7+ sectors rather than raising. If you need to reject high sector counts, check `num_sectors` before calling.

## Running the tests

```sh
PYTHONPATH=src python -m unittest discover -s tests
```

## Exports

- `DutyCalculator` — main calculation class; see `max_fdp`, `max_duty_minutes`, `min_rest_minutes`, `calculate`, `rest_in_window`.
- `Duration` — immutable integer-minute duration with arithmetic and comparison operators.
- `parse_duration` — strict `HH:MM` parser returning `Duration`.
- `DutyResult` — dataclass returned by `calculate` with `max_fdp`, `min_rest`, and `factors`.

## Deliberately unsupported

- Split duty, in-flight rest, augmented crew — these require crew-rest context that the caller must curate. `calculate` raises rather than guessing.
- Timezone conversion — the caller owns the clock.
- Parsing partial or malformed durations — `parse_duration` raises on anything not matching `^\d{2}:\d{2}$` with minutes in `[0, 59]`.

## Design notes

The window stores values eagerly rather than keeping running aggregates. Running
sums drift with floating point over long streams, and recomputing from a small
buffer is cheap enough that the drift is not worth the speed.

