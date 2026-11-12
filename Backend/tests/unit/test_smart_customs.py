import hashlib
import unittest

from smart_customs import CustomsPreClearance


class CustomsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.customs = CustomsPreClearance()
        self.cargo = {"weight": 100, "type": "Зерно", "sender": "A", "recipient": "B"}

    def test_canonical_hash_and_key_order(self) -> None:
        canonical = '{"recipient":"B","sender":"A","type":"Зерно","weight":100.0}'
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self.assertEqual(self.customs.calculate_cargo_hash(self.cargo), expected)
        reordered = dict(reversed(list(self.cargo.items())))
        self.assertTrue(self.customs.verify_cargo_hash(reordered, expected.upper()))

    def test_each_field_is_protected(self) -> None:
        digest = self.customs.calculate_cargo_hash(self.cargo)
        for field, value in [("weight", 101), ("type", "Oil"), ("sender", "B"), ("recipient", "A")]:
            with self.subTest(field=field):
                self.assertFalse(self.customs.verify_cargo_hash({**self.cargo, field: value}, digest))

    def test_invalid_hash_and_cargo(self) -> None:
        for digest in ("", "invalid", "g" * 64, "0" * 64):
            self.assertFalse(self.customs.verify_cargo_hash(self.cargo, digest))
        for weight in (-1, 0, True, "100", float("nan"), float("inf")):
            with self.subTest(weight=weight), self.assertRaises(ValueError):
                self.customs.calculate_cargo_hash({**self.cargo, "weight": weight})
        with self.assertRaises(ValueError):
            self.customs.calculate_cargo_hash({**self.cargo, "sender": "  "})
