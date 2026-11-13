"""Train the existing sea/land predictors and a separate terminal-readiness head."""
from __future__ import annotations
import json
import os
from uuid import uuid4
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from ml_pipeline import CaspianPredictor, FEATURE_COLUMNS as SEA_COLUMNS
from ml_predictor import TransitPredictor, FEATURE_COLUMNS as LAND_COLUMNS
from synthetic_scenarios import DATA_VERSION, SEED, SAMPLES, generate_training_episodes, sea_projection, land_projection

READY_COLUMNS = ('queue_units', 'service_hours', 'active_berths', 'remaining_service_hours')

@dataclass
class DemoModels:
    sea: CaspianPredictor
    land: TransitPredictor
    readiness: RandomForestRegressor
    report: dict[str, object]
    errors: dict[str, float]

    def predict(self, target: str, features: dict[str, object]) -> dict[str, object]:
        if target == 'sea':
            value = self.sea.predict(features)
            model_id = 'CaspianPredictor/demo-sea-v1'
        elif target == 'land':
            value = self.land.predict_delay(features)
            model_id = 'TransitPredictor/demo-land-v1'
        elif target == 'readiness':
            frame = pd.DataFrame([features], columns=list(READY_COLUMNS))
            value = float(self.readiness.predict(frame)[0])
            model_id = 'TerminalReadinessPredictor/demo-ready-v1'
        else:
            raise ValueError('Unknown prediction target')
        radius = self.errors[target]
        return {'model_id': model_id, 'target': target, 'value_hours': max(0.0, value),
                'lower_hours': max(0.0, value - radius), 'upper_hours': value + radius,
                'features': features, 'data_version': DATA_VERSION}


@lru_cache(maxsize=1)
def get_demo_models() -> DemoModels:
    frame = generate_training_episodes()
    train = frame.iloc[:14000]; calibration = frame.iloc[14000:17000]; test = frame.iloc[17000:]
    sea_train = sea_projection(train); land_train = land_projection(train)
    sea = CaspianPredictor().train(sea_train)
    land = TransitPredictor().train(land_train)
    ready = RandomForestRegressor(n_estimators=100, min_samples_leaf=2, n_jobs=1, random_state=SEED)
    ready.fit(train[list(READY_COLUMNS)], train.berth_ready_hours)
    models = DemoModels(sea, land, ready, {}, {})
    # Batch inference avoids repeating DataFrame construction for 6000 rows.
    def predictions(part: pd.DataFrame, target: str) -> np.ndarray:
        if target == 'sea': return sea.pipeline.predict(sea_projection(part)[list(SEA_COLUMNS)])
        if target == 'land': return land._pipeline.predict(land_projection(part)[list(LAND_COLUMNS)])
        return ready.predict(part[list(READY_COLUMNS)])
    metrics: dict[str, object] = {}
    for name, column in [('sea', 'sea_delay_hours'), ('land', 'land_delay_hours'), ('readiness', 'berth_ready_hours')]:
        calibration_errors = np.abs(calibration[column].to_numpy() - predictions(calibration, name))
        radius = float(np.quantile(calibration_errors, 0.90, method='higher'))
        models.errors[name] = radius
        estimate = predictions(test, name)
        actual = test[column].to_numpy(); absolute = np.abs(actual - estimate)
        mae = float(mean_absolute_error(actual, estimate))
        baseline = float(mean_absolute_error(actual, np.full(len(actual), train[column].mean())))
        metrics[name] = {'mae_hours': mae, 'baseline_mae_hours': baseline,
            'p90_absolute_error_hours': float(np.quantile(absolute, 0.90)), 'calibration_radius_hours': radius,
            'test_interval_coverage': float(np.mean(absolute <= radius)), 'test_count': len(test),
            'passes_mae_gate': mae <= 0.75 * baseline}
    models.report = {'data_source': 'synthetic', 'data_version': DATA_VERSION, 'seed': SEED,
        'samples': SAMPLES, 'split': {'train':14000, 'calibration':3000, 'test':3000},
        'split_method':'chronological, distinct episode_id; demo cases excluded',
        'metrics': metrics, 'interval_note': '90% absolute residual radius on calibration; coverage measured separately on test',
        'target_semantics': {'sea':'movement delay only; excludes berth queues', 'land':'movement delay only; excludes border wait and departure slots', 'readiness':'hours from decision until berth ready'}}
    output = Path(__file__).resolve().parent / 'artifacts' / 'synthetic-demo'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'model_report.json').write_text(json.dumps(models.report, ensure_ascii=False, indent=2), encoding='utf-8')
    artifact = output / f'models-{uuid4().hex}.tmp'
    try:
        joblib.dump(models, artifact)
        os.replace(artifact, output / 'models.joblib')
    finally:
        if artifact.exists():
            artifact.unlink()
    return models
