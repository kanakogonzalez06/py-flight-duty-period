# py_flight_duty_period — behaviour tests for the core FDP rules.
#
# Deterministic by construction: no wall-clock calls, no sleeps, no float
# equality. Every limit used here is defined in core.py.

import unittest

from py_flight_duty_period import (
    DutyCalculator,
    Duration,
    DutyResult,
    parse_duration,
)


class TestDuration(unittest.TestCase):
    def test_minutes(self):
        self.assertEqual(Duration(130).minutes, 130)

    def test_parse_hhmm(self):
        self.assertEqual(parse_duration("02:10"), Duration(130))

    def test_parse_zero(self):
        self.assertEqual(parse_duration("00:00"), Duration(0))

    def test_parse_rejects_bad_format(self):
        with self.assertRaises(ValueError):
            parse_duration("2:10")
        with self.assertRaises(ValueError):
            parse_duration("02:1")
        with self.assertRaises(ValueError):
            parse_duration("02-10")

    def test_parse_rejects_non_numeric(self):
        with self.assertRaises(ValueError):
            parse_duration("0a:10")
        with self.assertRaises(ValueError):
            parse_duration("02:b0")

    def test_parse_rejects_negative(self):
        with self.assertRaises(ValueError):
            parse_duration("-02:10")

    def test_parse_rejects_bad_minutes(self):
        with self.assertRaises(ValueError):
            parse_duration("02:60")
        with self.assertRaises(ValueError):
            parse_duration("02:99")

    def test_rejects_non_int(self):
        with self.assertRaises(TypeError):
            Duration(1.5)
        with self.assertRaises(TypeError):
            Duration("130")

    def test_rejects_negative(self):
        with self.assertRaises(ValueError):
            Duration(-5)

    def test_immutable(self):
        d = Duration(10)
        with self.assertRaises(AttributeError):
            d.minutes = 20

    def test_add(self):
        self.assertEqual(Duration(60) + Duration(30), Duration(90))

    def test_add_type_error(self):
        with self.assertRaises(TypeError):
            Duration(60) + 30

    def test_sub(self):
        self.assertEqual(Duration(90) - Duration(30), Duration(60))

    def test_sub_negative(self):
        with self.assertRaises(ValueError):
            Duration(30) - Duration(60)

    def test_sub_type_error(self):
        with self.assertRaises(TypeError):
            Duration(60) - 30

    def test_ordering(self):
        self.assertTrue(Duration(60) > Duration(30))
        self.assertTrue(Duration(30) < Duration(60))
        self.assertTrue(Duration(60) >= Duration(60))
        self.assertTrue(Duration(60) <= Duration(60))

    def test_str(self):
        self.assertEqual(str(Duration(130)), "02:10")

    def test_str_zero(self):
        self.assertEqual(str(Duration(0)), "00:00")

    def test_str_under_60(self):
        self.assertEqual(str(Duration(30)), "00:30")

    def test_repr(self):
        self.assertEqual(repr(Duration(130)), "Duration(minutes=130)")

    def test_hash(self):
        self.assertEqual(hash(Duration(130)), hash(Duration(130)))
        self.assertEqual(hash(Duration(130)), hash(130))


class TestMaxFdp(unittest.TestCase):
    def setUp(self):
        self.calc = DutyCalculator()

    def test_sector_limits(self):
        cases = [
            (1, 13 * 60),
            (2, 11 * 60 + 30),
            (3, 11 * 60),
            (4, 10 * 60 + 30),
            (5, 10 * 60),
            (6, 9 * 60 + 30),
            (7, 9 * 60),
        ]
        for sectors, expected in cases:
            with self.subTest(sectors=sectors):
                self.assertEqual(self.calc.max_fdp(sectors), expected)

    def test_more_than_seven_uses_cap(self):
        self.assertEqual(self.calc.max_fdp(8), self.calc.max_fdp(7))
        self.assertEqual(self.calc.max_fdp(20), self.calc.max_fdp(7))

    def test_invalid_type(self):
        with self.assertRaises(TypeError):
            self.calc.max_fdp("1")

    def test_zero_sectors(self):
        with self.assertRaises(ValueError):
            self.calc.max_fdp(0)

    def test_negative_sectors(self):
        with self.assertRaises(ValueError):
            self.calc.max_fdp(-1)


class TestMaxDuty(unittest.TestCase):
    def setUp(self):
        self.calc = DutyCalculator()

    def test_compose_duty(self):
        self.assertEqual(self.calc.max_duty_minutes(600, 60, 30), 690)

    def test_rejects_non_int(self):
        with self.assertRaises(TypeError):
            self.calc.max_duty_minutes("600", 60, 30)
        with self.assertRaises(TypeError):
            self.calc.max_duty_minutes(600, 60.0, 30)
        with self.assertRaises(TypeError):
            self.calc.max_duty_minutes(600, 60, None)

    def test_rejects_negative(self):
        with self.assertRaises(ValueError):
            self.calc.max_duty_minutes(-1, 60, 30)

    def test_exceeds_max_duty_raises(self):
        with self.assertRaises(ValueError):
            self.calc.max_duty_minutes(800, 30, 30)

    def test_at_max_passes(self):
        self.assertEqual(
            self.calc.max_duty_minutes(13 * 60, 30, 30),
            14 * 60,
        )


class TestMinRest(unittest.TestCase):
    def setUp(self):
        self.calc = DutyCalculator()

    def test_short_fdp_uses_flat_minimum(self):
        self.assertEqual(self.calc.min_rest_minutes(60), 12 * 60)

    def test_at_12h_fdp_uses_flat(self):
        self.assertEqual(self.calc.min_rest_minutes(12 * 60), 18 * 60)

    def test_at_14h_fdp_still_flat(self):
        self.assertEqual(self.calc.min_rest_minutes(14 * 60), 21 * 60)

    def test_long_fdp_uses_150_pct(self):
        self.assertEqual(self.calc.min_rest_minutes(15 * 60), 22 * 60 + 30)

    def test_rejects_non_int(self):
        with self.assertRaises(TypeError):
            self.calc.min_rest_minutes("600")
        with self.assertRaises(TypeError):
            self.calc.min_rest_minutes(600.0)
        with self.assertRaises(TypeError):
            self.calc.min_rest_minutes(None)

    def test_rejects_negative(self):
        with self.assertRaises(ValueError):
            self.calc.min_rest_minutes(-1)


class TestCalculate(unittest.TestCase):
    def setUp(self):
        self.calc = DutyCalculator()

    def test_day_single_sector(self):
        result = self.calc.calculate(
            reporting_time="2024-01-15 06:00",
            time_airborne="2024-01-15 06:30",
            num_sectors=1,
            block_off_minute=6 * 60,
            block_on_minute=7 * 60 + 30,
            post_flight_minutes=30,
        )
        self.assertIsInstance(result, DutyResult)
        self.assertEqual(result.max_fdp, 13 * 60)
        self.assertEqual(result.min_rest, 12 * 60)
        self.assertEqual(result.factors["pre_flight_minutes"], 30)
        self.assertEqual(result.factors["post_flight_minutes"], 30)
        self.assertEqual(result.factors["fdp_minutes"], 120)
        self.assertEqual(result.factors["duty_minutes"], 180)
        self.assertEqual(result.factors["sectors"], 1)

    def test_multi_sector(self):
        result = self.calc.calculate(
            reporting_time="2024-02-20 05:00",
            time_airborne="2024-02-20 05:45",
            num_sectors=3,
            block_off_minute=5 * 60,
            block_on_minute=15 * 60,
            post_flight_minutes=30,
        )
        self.assertEqual(result.max_fdp, 11 * 60)
        self.assertEqual(result.factors["pre_flight_minutes"], 45)
        self.assertEqual(result.factors["fdp_minutes"], 10 * 60 + 45)
        self.assertEqual(result.factors["duty_minutes"], 12 * 60)
        self.assertEqual(result.factors["sectors"], 3)
        self.assertEqual(result.min_rest, 16 * 60 + 7)

    def test_post_flight_defaults_to_30(self):
        result = self.calc.calculate(
            reporting_time="2024-01-15 06:00",
            time_airborne="2024-01-15 06:30",
            num_sectors=1,
            block_off_minute=6 * 60,
            block_on_minute=7 * 60,
        )
        self.assertEqual(result.factors["post_flight_minutes"], 30)

    def test_rejects_reporting_after_airborne(self):
        with self.assertRaises(ValueError):
            self.calc.calculate(
                reporting_time="2024-01-15 07:00",
                time_airborne="2024-01-15 06:30",
                num_sectors=1,
                block_off_minute=6 * 60,
                block_on_minute=7 * 60,
            )

    def test_rejects_block_off_before_reporting(self):
        with self.assertRaises(ValueError):
            self.calc.calculate(
                reporting_time="2024-01-15 06:30",
                time_airborne="2024-01-15 06:00",
                num_sectors=1,
                block_off_minute=5 * 60,
                block_on_minute=7 * 60,
            )

    def test_rejects_block_on_before_off(self):
        with self.assertRaises(ValueError):
            self.calc.calculate(
                reporting_time="2024-01-15 06:00",
                time_airborne="2024-01-15 06:30",
                num_sectors=1,
                block_off_minute=7 * 60,
                block_on_minute=6 * 60,
            )

    def test_rejects_zero_sectors(self):
        with self.assertRaises(ValueError):
            self.calc.calculate(
                reporting_time="2024-01-15 06:00",
                time_airborne="2024-01-15 06:30",
                num_sectors=0,
                block_off_minute=6 * 60,
                block_on_minute=7 * 60,
            )

    def test_rejects_non_int_sectors(self):
        with self.assertRaises(TypeError):
            self.calc.calculate(
                reporting_time="2024-01-15 06:00",
                time_airborne="2024-01-15 06:30",
                num_sectors="1",
                block_off_minute=6 * 60,
                block_on_minute=7 * 60,
            )

    def test_duty_exceeds_14h_raises(self):
        with self.assertRaises(ValueError):
            self.calc.calculate(
                reporting_time="2024-01-15 06:00",
                time_airborne="2024-01-15 06:30",
                num_sectors=1,
                block_off_minute=6 * 60,
                block_on_minute=20 * 60,
                post_flight_minutes=30,
            )

    def test_bad_timestamp_format(self):
        with self.assertRaises(ValueError):
            self.calc.calculate(
                reporting_time="2024/01/15 06:00",
                time_airborne="2024-01-15 06:30",
                num_sectors=1,
                block_off_minute=6 * 60,
                block_on_minute=7 * 60,
            )

    def test_bad_timestamp_length(self):
        with self.assertRaises(ValueError):
            self.calc.calculate(
                reporting_time="2024-01-15 6:00",
                time_airborne="2024-01-15 06:30",
                num_sectors=1,
                block_off_minute=6 * 60,
                block_on_minute=7 * 60,
            )

    def test_bad_timestamp_field(self):
        with self.assertRaises(ValueError):
            self.calc.calculate(
                reporting_time="2024-13-15 06:00",
                time_airborne="2024-01-15 06:30",
                num_sectors=1,
                block_off_minute=6 * 60,
                block_on_minute=7 * 60,
            )
        with self.assertRaises(ValueError):
            self.calc.calculate(
                reporting_time="2024-01-15 06:00",
                time_airborne="2024-01-15 24:30",
                num_sectors=1,
                block_off_minute=6 * 60,
                block_on_minute=7 * 60,
            )

    def test_reporting_non_string(self):
        with self.assertRaises(TypeError):
            self.calc.calculate(
                reporting_time=12345,
                time_airborne="2024-01-15 06:30",
                num_sectors=1,
                block_off_minute=6 * 60,
                block_on_minute=7 * 60,
            )

    def test_block_off_non_int(self):
        with self.assertRaises(TypeError):
            self.calc.calculate(
                reporting_time="2024-01-15 06:00",
                time_airborne="2024-01-15 06:30",
                num_sectors=1,
                block_off_minute="360",
                block_on_minute=7 * 60,
            )

    def test_post_flight_non_int(self):
        with self.assertRaises(TypeError):
            self.calc.calculate(
                reporting_time="2024-01-15 06:00",
                time_airborne="2024-01-15 06:30",
                num_sectors=1,
                block_off_minute=6 * 60,
                block_on_minute=7 * 60,
                post_flight_minutes="30",
            )


class TestRestWindow(unittest.TestCase):
    def setUp(self):
        self.calc = DutyCalculator()

    def test_empty_epochs(self):
        self.assertEqual(self.calc.rest_in_window([], 600), 0)

    def test_single_rest_in_window(self):
        epochs = [(0, 600, 0)]
        self.assertEqual(self.calc.rest_in_window(epochs, 600), 600)

    def test_duty_kind_ignored(self):
        epochs = [(0, 600, 1)]
        self.assertEqual(self.calc.rest_in_window(epochs, 600), 0)

    def test_rest_partially_outside_window(self):
        epochs = [(0, 1500, 0)]
        self.assertEqual(self.calc.rest_in_window(epochs, 1500), 1440)

    def test_rest_far_in_past_not_counted(self):
        epochs = [(0, 120, 0)]
        self.assertEqual(self.calc.rest_in_window(epochs, 2000), 0)

    def test_invalid_kind_rejected(self):
        epochs = [(0, 600, 5)]
        with self.assertRaises(ValueError):
            self.calc.rest_in_window(epochs, 600)

    def test_rejects_non_int_end(self):
        with self.assertRaises(TypeError):
            self.calc.rest_in_window([], "600")

    def test_rejects_non_int_block_start(self):
        epochs = [("0", 600, 0)]
        with self.assertRaises(TypeError):
            self.calc.rest_in_window(epochs, 600)

    def test_rejects_negative_block_start(self):
        epochs = [(-1, 600, 0)]
        with self.assertRaises(ValueError):
            self.calc.rest_in_window(epochs, 600)


if __name__ == "__main__":
    unittest.main()
