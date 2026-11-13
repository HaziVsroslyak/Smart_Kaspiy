"""Behavioral proof for the synthetic ML/JIT demonstration, independent of live APIs."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from demo_contracts import DemoRunRequest
from demo_models import get_demo_models
from jit_optimizer import CO2_FACTOR, MIN_SPEED_KNOTS
from jit_service import ANCHOR, SCENARIOS, run_scenario, slot_after
from synthetic_scenarios import generate_training_episodes, sea_projection, land_projection
from voyage_store import VoyageStore


class SyntheticDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.episodes = generate_training_episodes()
        cls.models = get_demo_models()
        with patch('weather_service.urlopen', side_effect=AssertionError('Synthetic demo must not access weather APIs')):
            cls.results = {scene.id: run_scenario(scene.id, DemoRunRequest(), cls.models) for scene in SCENARIOS}

    @staticmethod
    def strategies(result):
        return {strategy.id: strategy for strategy in result.strategies}

    def test_episodes_are_reproducible_disjoint_and_available_at_decision(self) -> None:
        data = self.episodes
        self.assertEqual(len(data), 20_000)
        self.assertTrue(data.episode_id.is_unique)
        self.assertTrue(data.shipment_id.is_unique)
        self.assertTrue(data.decision_at.is_monotonic_increasing)
        self.assertTrue((data.issued_at <= data.decision_at).all())
        self.assertTrue((data.valid_at > data.decision_at).all())
        self.assertEqual(set(data.scenario_id), {'generated'})
        self.assertTrue(set(data.scenario_id).isdisjoint(scene.id for scene in SCENARIOS))
        train, calibration, test = data.iloc[:14000], data.iloc[14000:17000], data.iloc[17000:]
        for left, right in ((train, calibration), (train, test), (calibration, test)):
            self.assertTrue(set(left.episode_id).isdisjoint(right.episode_id))
            self.assertLess(left.decision_at.max(), right.decision_at.min())
        pd.testing.assert_frame_equal(generate_training_episodes(100), generate_training_episodes(100))
        self.assertFalse(generate_training_episodes(100).equals(generate_training_episodes(100, seed=7)))
        forbidden = {'actual_arrival', 'berth_ready_hours', 'sea_delay_hours', 'land_delay_hours', 'episode_id'}
        for projection in (sea_projection(data), land_projection(data)):
            self.assertTrue(forbidden.isdisjoint(projection.columns))

    def test_each_model_beats_constant_holdout_baseline(self) -> None:
        report = self.models.report
        self.assertEqual(report['samples'], 20_000)
        self.assertEqual(report['split'], {'train':14000, 'calibration':3000, 'test':3000})
        for target, metric in report['metrics'].items():
            with self.subTest(target=target):
                self.assertTrue(metric['passes_mae_gate'])
                self.assertLessEqual(metric['mae_hours'], 0.75 * metric['baseline_mae_hours'])
                self.assertGreaterEqual(metric['p90_absolute_error_hours'], 0)
                self.assertGreaterEqual(metric['test_interval_coverage'], 0)
                self.assertLessEqual(metric['test_interval_coverage'], 1)

    def test_model_dispatch_uses_fitted_sea_land_and_terminal_heads(self) -> None:
        with patch.object(self.models.sea, 'predict', wraps=self.models.sea.predict) as sea, \
             patch.object(self.models.land, 'predict_delay', wraps=self.models.land.predict_delay) as land, \
             patch.object(self.models.readiness, 'predict', wraps=self.models.readiness.predict) as readiness:
            result = run_scenario('calm', DemoRunRequest(), self.models)
        self.assertGreater(sea.call_count, 0)
        self.assertGreater(land.call_count, 0)
        self.assertGreater(readiness.call_count, 0)
        self.assertEqual({trace.target for trace in result.predictions}, {'sea', 'land', 'readiness'})
        for trace in result.predictions:
            self.assertLessEqual(trace.lower_hours, trace.value_hours)
            self.assertGreaterEqual(trace.upper_hours, trace.value_hours)
            self.assertNotIn('actual_arrival', trace.features)

    def test_all_eight_cases_return_consistent_time_and_fuel(self) -> None:
        self.assertEqual(len(self.results), 8)
        scene_by_id = {scene.id: scene for scene in SCENARIOS}
        for identity, result in self.results.items():
            scene = scene_by_id[identity]
            self.assertEqual(result.data_source, 'synthetic')
            self.assertEqual(result.baseline, self.strategies(result)['baseline'])
            for strategy in result.strategies:
                with self.subTest(scenario=identity, strategy=strategy.id):
                    if strategy.status != 'ok':
                        self.assertIsNone(strategy.speed_knots)
                        self.assertIsNone(strategy.fuel_saved_tonnes)
                        self.assertIsNone(strategy.co2_saved_tonnes)
                        continue
                    self.assertGreaterEqual(strategy.berth_wait_hours, 0)
                    self.assertGreaterEqual(strategy.connection_wait_hours, 0)
                    self.assertAlmostEqual(strategy.total_time_hours, (strategy.eta - ANCHOR).total_seconds()/3600, places=7)
                    self.assertAlmostEqual(strategy.total_time_hours, sum(leg.expected_time_hours for leg in strategy.segments), places=7)
                    times = [event.at for event in strategy.timeline]
                    self.assertEqual(times, sorted(times))
                    if strategy.id != 'alternative':
                        self.assertGreaterEqual(strategy.speed_knots, MIN_SPEED_KNOTS)
                        self.assertLessEqual(strategy.speed_knots, scene.speed)
                        self.assertAlmostEqual(strategy.co2_tonnes, strategy.fuel_tonnes * CO2_FACTOR)
                        self.assertLessEqual(strategy.handling_complete_at, strategy.connection_at)
            options = self.strategies(result)
            if options['jit'].status == 'ok':
                self.assertLessEqual(options['jit'].eta, options['baseline'].eta)
                self.assertLessEqual(options['jit'].fuel_tonnes, options['baseline'].fuel_tonnes)
                self.assertAlmostEqual(options['jit'].fuel_saved_tonnes,
                                       options['baseline'].fuel_tonnes - options['jit'].fuel_tonnes)
                self.assertAlmostEqual(options['jit'].co2_saved_tonnes, options['jit'].fuel_saved_tonnes * CO2_FACTOR)

    def test_calm_does_not_slow_without_a_berth_constraint(self) -> None:
        result = self.strategies(self.results['calm'])
        self.assertEqual(result['jit'].speed_knots, result['baseline'].speed_knots)
        self.assertEqual(result['jit'].fuel_saved_tonnes, 0)

    def test_queue_slows_and_reduces_anchor_wait_without_later_eta(self) -> None:
        result = self.strategies(self.results['berth_queue'])
        self.assertLess(result['jit'].speed_knots, result['baseline'].speed_knots)
        self.assertLess(result['jit'].berth_wait_hours, result['baseline'].berth_wait_hours)
        self.assertLessEqual(result['jit'].eta, result['baseline'].eta)
        self.assertGreater(result['jit'].co2_saved_tonnes, 0)
        self.assertGreater(result['jit'].checkpoints[1].passage_at, result['baseline'].checkpoints[1].passage_at)

    def test_minimum_speed_leaves_unavoidable_wait(self) -> None:
        result = self.strategies(self.results['minimum_speed'])['jit']
        self.assertAlmostEqual(result.speed_knots, MIN_SPEED_KNOTS, places=6)
        self.assertGreater(result.remaining_wait_hours, 0)
        self.assertEqual(result.remaining_wait_hours, result.berth_wait_hours)

    def test_storm_and_missing_weather_do_not_claim_a_safe_speed_or_savings(self) -> None:
        for identity, expected in [('storm', 'blocked'), ('missing_weather', 'insufficient_data')]:
            for strategy in self.results[identity].strategies[:2]:
                self.assertEqual(strategy.status, expected)
                self.assertIsNone(strategy.speed_knots)
                self.assertIsNone(strategy.eta)
                self.assertIsNone(strategy.co2_saved_tonnes)
        missing = self.results['missing_weather'].baseline
        self.assertTrue(all(point.wave_height_m is None for point in missing.checkpoints))

    def test_missed_train_and_exact_cutoff(self) -> None:
        self.assertEqual(slot_after(38, 38, 48), 38)
        self.assertEqual(slot_after(38.001, 38, 48), 86)
        result = self.results['missed_train'].baseline
        self.assertIn('Пропущен', result.reason)
        self.assertEqual((result.connection_at - ANCHOR).total_seconds()/3600, 86)
        self.assertGreater(result.connection_wait_hours, 0)

    def test_runs_are_reproducible_and_saved_baseline_is_immutable(self) -> None:
        first = self.results['berth_queue']
        second = run_scenario('berth_queue', DemoRunRequest(), self.models)
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(first.model_dump(exclude={'id','created_at'}), second.model_dump(exclude={'id','created_at'}))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'demo.sqlite3'
            VoyageStore(path).save_demo(first)
            restored = VoyageStore(path).get_demo(first.id)
            self.assertEqual(restored, first)
            with self.assertRaises(sqlite3.IntegrityError):
                VoyageStore(path).save_demo(first)
            VoyageStore(path).save_demo(second)
            self.assertEqual(VoyageStore(path).get_demo(first.id).baseline, first.baseline)
            with self.assertRaises(KeyError):
                VoyageStore(path).get_demo('missing')
