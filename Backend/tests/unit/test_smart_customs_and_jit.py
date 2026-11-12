import hashlib
import unittest

from smart_customs import CustomsPreClearance
from smart_customs_and_jit import (
    calculate_customs_hash, optimize_vessel_speed, verify_customs_hash,
)


class CombinedBusinessTests(unittest.TestCase):
    def test_id_payload_canonicalization(self) -> None:
        cargo = {"weight": 100, "type": "Зерно", "id": "C-001"}
        canonical = '{"id":"C-001","type":"Зерно","weight":100.0}'
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self.assertEqual(calculate_customs_hash(cargo), expected)
        reordered = {"id": "C-001", "type": "Зерно", "weight": 100.0}
        self.assertTrue(verify_customs_hash(reordered, expected.upper()))
        for field, value in [("id", "C-002"), ("type", "Oil"), ("weight", 101)]:
            with self.subTest(field=field):
                self.assertFalse(verify_customs_hash({**cargo, field: value}, expected))

    def test_legacy_hash_remains_compatible(self) -> None:
        cargo = {"weight": 100, "type": "Зерно", "sender": "A", "recipient": "B"}
        digest = CustomsPreClearance.calculate_cargo_hash(cargo)
        self.assertTrue(verify_customs_hash(cargo, digest))

    def test_invalid_cargo_and_hash(self) -> None:
        cargo = {"weight": 100, "type": "Зерно", "id": "C-001"}
        for digest in ("", "0" * 64, "g" * 64):
            self.assertFalse(verify_customs_hash(cargo, digest))
        for invalid in ({"weight": 100, "type": "Зерно"}, {**cargo, "id": " "},
                        {**cargo, "extra": "data"}, {**cargo, "weight": -1},
                        {**cargo, "weight": float("nan")}):
            with self.subTest(cargo=invalid), self.assertRaises(ValueError):
                calculate_customs_hash(invalid)

    def test_combined_jit_result(self) -> None:
        result = optimize_vessel_speed(120, 12, 5)
        self.assertEqual(result["new_speed_knots"], 8)
        self.assertEqual(result["arrival_in_hours"], 15)
        self.assertEqual(result["berth_available_in_hours"], 15)
        self.assertEqual(result["remaining_wait_hours"], 0)
        self.assertAlmostEqual(result["baseline_fuel_tonnes"], 1.728)
        self.assertAlmostEqual(result["optimized_fuel_tonnes"], 0.768)
        self.assertAlmostEqual(result["fuel_saved_tonnes"], 0.96)
        self.assertAlmostEqual(result["co2_saved_tonnes"], 2.98944)

    def test_jit_boundaries_and_validation(self) -> None:
        clear_port = optimize_vessel_speed(120, 12, 0)
        self.assertEqual(clear_port["new_speed_knots"], 12)
        self.assertEqual(clear_port["co2_saved_tonnes"], 0)
        busy_port = optimize_vessel_speed(120, 12, 30)
        self.assertEqual(busy_port["new_speed_knots"], 6)
        self.assertEqual(busy_port["remaining_wait_hours"], 20)
        for values in [(0, 12, 5), (120, 5, 5), (120, 12, -1), (120, True, 5)]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                optimize_vessel_speed(*values)
