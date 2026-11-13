"""Export reproducible episodes and train/report the demonstration models."""
from pathlib import Path
import json
from synthetic_scenarios import Episode, generate_training_episodes
from demo_models import get_demo_models

def main() -> None:
    root=Path(__file__).resolve().parents[1]
    target=root/'data'/'processed';target.mkdir(parents=True,exist_ok=True)
    episodes=generate_training_episodes()
    episodes['split']=['train']*14000+['calibration']*3000+['test']*3000
    episodes.to_csv(target/'synthetic_episodes.csv',index=False,encoding='utf-8')
    (root/'contracts'/'scenario_episode.json').write_text(json.dumps(Episode.model_json_schema(),ensure_ascii=False,indent=2),encoding='utf-8')
    report=get_demo_models().report
    print(json.dumps(report,ensure_ascii=False,indent=2))
    print(f'Exported {len(episodes)} episodes to {target}')

if __name__=='__main__': main()
