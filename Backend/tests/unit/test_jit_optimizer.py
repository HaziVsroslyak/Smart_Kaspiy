import unittest

from jit_optimizer import calculate_esg, optimize_speed


class JITTests(unittest.TestCase):
    def test_exact_arrival(self) -> None:
        speed = optimize_speed(120, 12, 5)
        self.assertEqual(speed, 8)
        self.assertEqual(120 / speed, 120 / 12 + 5)

    def test_no_delay_and_minimum_speed(self) -> None:
        self.assertEqual(optimize_speed(120, 12, 0), 12)
        self.assertEqual(optimize_speed(120, 12, 10), 6)
        self.assertEqual(optimize_speed(120, 12, 30), 6)
        self.assertEqual(optimize_speed(120, 6, 30), 6)

    def test_voyage_fuel_not_hourly_rate(self) -> None:
        result = calculate_esg(120, 12, 8)
        self.assertAlmostEqual(result["baseline_fuel_tonnes"], 1.728)
        self.assertAlmostEqual(result["optimized_fuel_tonnes"], 0.768)
        self.assertAlmostEqual(result["fuel_saved_tonnes"], 0.96)
        self.assertAlmostEqual(result["co2_saved_tonnes"], 2.98944)
        self.assertEqual(calculate_esg(120, 12, 12)["fuel_saved_tonnes"], 0)

    def test_calibration_and_distance_scale_linearly(self) -> None:
        base = calculate_esg(120, 12, 8)["co2_saved_tonnes"]
        self.assertAlmostEqual(calculate_esg(240, 12, 8)["co2_saved_tonnes"], 2 * base)
        self.assertAlmostEqual(calculate_esg(120, 12, 8, fuel_coefficient=0.0002)["co2_saved_tonnes"], 2 * base)

    def test_invalid_inputs(self) -> None:
        for args in [(0, 12, 5), (-1, 12, 5), (120, 5, 5), (120, 12, -1),
                     (True, 12, 5), (120, "12", 5), (float("nan"), 12, 5),
                     (120, 12, float("inf")), (1e-320, 1e308, 0)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                optimize_speed(*args)
        for args in [(120, 12, 15), (120, 12, 5), (0, 12, 8), (120, float("inf"), 8), (120, 1e308, 8)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                calculate_esg(*args)
        with self.assertRaises(ValueError):
            calculate_esg(120, 12, 8, fuel_coefficient=0)
