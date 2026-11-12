"""Run from Backend: python -m scripts.export_contracts"""
import json
from pathlib import Path
from main import app
from ml_pipeline import CaspianFeatures, _TrainingRecord, generate_mock_data

def main() -> None:
    target = Path(__file__).resolve().parents[1] / 'contracts'
    target.mkdir(exist_ok=True)
    for name, schema in [('openapi',app.openapi()),('caspian_features',CaspianFeatures.model_json_schema()),('training_record',_TrainingRecord.model_json_schema())]:
        (target / f'{name}.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2),encoding='utf-8')
    generate_mock_data(10).to_csv(target/'training_sample.csv',index=False,encoding='utf-8')
    print(f'Contracts exported to {target}')

if __name__ == '__main__': main()
