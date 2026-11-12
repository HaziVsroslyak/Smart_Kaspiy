"""Behavioral checks for synthetic data, model quality and input validation."""

import math
import unittest

import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split

from ml_predictor import (
    CITIES, FEATURE_COLUMNS, ModelNotTrainedError, TransitFeatures,
    TransitPredictor, generate_mock_data,
)


class TransitPredictorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = generate_mock_data()
        cls.train_data, cls.test_data = train_test_split(
            cls.data, test_size=0.2, random_state=17,
        )
        cls.predictor = TransitPredictor().train(cls.train_data)

    def test_dataset_contract_and_reproducibility(self) -> None:
        self.assertEqual(len(self.data), 1000)
        pd.testing.assert_frame_equal(self.data, generate_mock_data())
        self.assertFalse(self.data.equals(generate_mock_data(99)))
        self.assertTrue(self.data.weather_severity.between(0, 10).all())
        self.assertTrue(self.data.port_congestion.between(0, 100).all())
        self.assertTrue((self.data.delay_hours >= 0).all())
        self.assertTrue((self.data.origin != self.data.destination).all())
        self.assertEqual(set(self.data.origin), set(CITIES))
        self.assertEqual(set(self.data.destination), set(CITIES))
        self.assertEqual(set(self.data.transport_mode), {"ship", "rail"})
        self.assertEqual(set(self.data.season), {"winter", "spring", "summer", "autumn"})
        self.assertFalse(self.data.isna().any().any())

    def test_untrained_model(self) -> None:
        with self.assertRaises(ModelNotTrainedError):
            TransitPredictor().predict_delay(self._features())

    @staticmethod
    def _features() -> dict[str, object]:
        return {"weather_severity": 7.0, "port_congestion": 80.0,
                "transport_mode": "ship", "season": "winter"}

    def test_prediction_contract_and_column_order(self) -> None:
        features = self._features()
        result = self.predictor.predict_delay(features)
        self.assertIsInstance(result, float)
        self.assertTrue(math.isfinite(result))
        self.assertGreaterEqual(result, 0)
        self.assertEqual(result, self.predictor.predict_delay(dict(reversed(list(features.items())))))
        self.assertEqual(result, self.predictor.predict_delay(TransitFeatures(**features)))

    def test_reject_invalid_features(self) -> None:
        for field, value in [
            ("weather_severity", -1), ("weather_severity", 11),
            ("weather_severity", float("nan")), ("port_congestion", float("inf")),
            ("port_congestion", 101), ("port_congestion", True),
            ("port_congestion", "80"), ("transport_mode", "truck"),
            ("season", "unknown"), ("delay_hours", 5),
        ]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.predictor.predict_delay({**self._features(), field: value})
        with self.assertRaises(ValueError):
            self.predictor.predict_delay({"season": "winter"})

    def test_failed_training_preserves_model(self) -> None:
        before = self.predictor.predict_delay(self._features())
        invalid = self.train_data.copy()
        invalid.loc[invalid.index[0], "delay_hours"] = -1
        for data in [invalid, self.data.iloc[:0], self.data.drop(columns="season")]:
            with self.assertRaises(ValueError):
                self.predictor.train(data)
        self.assertEqual(before, self.predictor.predict_delay(self._features()))

    def test_held_out_quality_beats_constant_baseline(self) -> None:
        # IID synthetic records have no timestamps; this is a random holdout.
        inputs = self.test_data[list(FEATURE_COLUMNS)]
        predictions = [self.predictor.predict_delay(row) for row in inputs.to_dict("records")]
        baseline = DummyRegressor(strategy="mean").fit(
            self.train_data[list(FEATURE_COLUMNS)], self.train_data.delay_hours,
        )
        model_mae = mean_absolute_error(self.test_data.delay_hours, predictions)
        baseline_mae = mean_absolute_error(self.test_data.delay_hours, baseline.predict(inputs))
        self.assertLess(model_mae, baseline_mae * 0.6)


if __name__ == "__main__":
    unittest.main()
