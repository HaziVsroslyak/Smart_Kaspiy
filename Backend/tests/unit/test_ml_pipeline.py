import math
import random
import unittest
from unittest.mock import Mock

import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.exceptions import NotFittedError
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split

from ml_pipeline import (
    ARRIVAL_PORTS, DEPARTURE_PORTS, FEATURE_COLUMNS, SEASONS,
    CaspianPredictor, _sample_delay, generate_mock_data,
)


class CaspianPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = generate_mock_data()
        cls.train_data, cls.test_data = train_test_split(cls.data, test_size=0.2, random_state=17)
        cls.predictor = CaspianPredictor().train(cls.train_data)

    @staticmethod
    def features() -> dict[str, object]:
        return {"departure_port": "Оля", "arrival_port": "Энзели",
                "wind_speed_ms": 18.0, "wave_height_m": 3.2,
                "port_congestion_percent": 90.0, "season": "Winter"}

    def test_data_contract_and_reproducibility(self) -> None:
        self.assertEqual(len(self.data), 5000)
        self.assertEqual(list(self.data.columns), [*FEATURE_COLUMNS, "delay_hours"])
        for column, choices in [("departure_port", DEPARTURE_PORTS),
                                ("arrival_port", ARRIVAL_PORTS), ("season", SEASONS)]:
            self.assertEqual(set(self.data[column]), set(choices))
        for column, lower, upper in [("wind_speed_ms", 0, 25), ("wave_height_m", 0.1, 4.5),
                                     ("port_congestion_percent", 10, 100)]:
            self.assertTrue(self.data[column].between(lower, upper).all())
        self.assertTrue((self.data.delay_hours >= 0).all())
        self.assertFalse(self.data.isna().any().any())
        pd.testing.assert_frame_equal(self.data, generate_mock_data())
        self.assertEqual(len(generate_mock_data(17)), 17)
        self.assertFalse(self.data.equals(generate_mock_data(random_state=43)))

    def test_scenario_thresholds_and_additive_delays(self) -> None:
        rng = Mock(spec=random.Random)
        rng.uniform.side_effect = lambda low, high: (low + high) / 2
        rng.gauss.return_value = 0.0
        cases = [
            ("Махачкала", 2.5, 85, "Winter", 2),
            ("Махачкала", 2.5001, 85, "Winter", 20),
            ("Махачкала", 2.5, 85.0001, "Winter", 25),
            ("Астрахань", 2.5, 85, "Winter", 38),
            ("Оля", 2.5, 85, "Winter", 38),
            ("Оля", 2.5, 85, "Summer", 2),
            ("Оля", 3.0, 90, "Winter", 79),
        ]
        for departure, wave, congestion, season, expected in cases:
            with self.subTest(departure=departure, wave=wave, congestion=congestion, season=season):
                self.assertEqual(_sample_delay(departure, wave, congestion, season, rng), expected)
        rng.gauss.return_value = -10.0
        self.assertEqual(_sample_delay("Махачкала", 1.0, 10, "Summer", rng), 0)

    def test_invalid_sample_counts(self) -> None:
        for value in (0, -1, True, 5.5, "10"):
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                generate_mock_data(value)

    def test_prediction_and_untrained_error(self) -> None:
        with self.assertRaises(NotFittedError):
            CaspianPredictor().predict(self.features())
        result = self.predictor.predict(self.features())
        self.assertIsInstance(result, float)
        self.assertTrue(math.isfinite(result))
        self.assertGreaterEqual(result, 0)
        reordered = dict(reversed(list(self.features().items())))
        self.assertEqual(result, self.predictor.predict(reordered))

    def test_invalid_features(self) -> None:
        for field, value in [("wind_speed_ms", 26), ("wave_height_m", 0),
                             ("port_congestion_percent", 9), ("season", "winter"),
                             ("departure_port", "Unknown"), ("arrival_port", "Оля"),
                             ("wind_speed_ms", True), ("wind_speed_ms", "18"),
                             ("wave_height_m", float("nan")), ("wave_height_m", float("inf")),
                             ("delay_hours", 10)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.predictor.predict({**self.features(), field: value})
        with self.assertRaises(ValueError):
            self.predictor.predict({"departure_port": "Оля"})

    def test_invalid_training_preserves_model(self) -> None:
        before = self.predictor.predict(self.features())
        negative_target = self.train_data.copy()
        negative_target.loc[negative_target.index[0], "delay_hours"] = -1
        duplicate_columns = pd.concat([self.train_data, self.train_data[["season"]]], axis=1)
        for df in (negative_target, duplicate_columns, self.train_data.iloc[:0],
                   self.train_data.drop(columns="arrival_port")):
            with self.assertRaises(ValueError):
                self.predictor.train(df)
        self.assertEqual(before, self.predictor.predict(self.features()))

    def test_holdout_beats_mean_baseline(self) -> None:
        # Independent synthetic rows have no timestamps; use random holdout.
        test = self.test_data.iloc[:200]
        inputs = test[list(FEATURE_COLUMNS)]
        predictions = [self.predictor.predict(row) for row in inputs.to_dict("records")]
        baseline = DummyRegressor(strategy="mean").fit(
            self.train_data[list(FEATURE_COLUMNS)], self.train_data.delay_hours,
        )
        model_mae = mean_absolute_error(test.delay_hours, predictions)
        baseline_mae = mean_absolute_error(test.delay_hours, baseline.predict(inputs))
        self.assertLess(model_mae, baseline_mae * 0.7)
