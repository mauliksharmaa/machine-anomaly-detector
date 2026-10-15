"""Trained model ko ALAG collect kiye data pe test karta hai (training data pe nahi).

Files (sab `python -m backend.collect_data --step 1 --out ...` se banao):
    ml/data/healthy_test.csv    healthy motor, training se alag session (glitch rows hataana nahi)
    ml/data/anomaly_*.csv       safe, deliberately induced anomaly (ek file per test)

Run (project root se):
    python -m ml.evaluate

Live backend har LIVE_STEP-th reading pe window judge karta hai, aur STOP ke liye lagatar
CONSECUTIVE_LIMIT windows chahiye. Yahan wahi rule step-1 file pe chalaya jata hai.
Healthy file pe 0 STOP, anomaly files pe >=1 STOP aana chahiye. Ye chhote tests hain:
"accuracy" mat likhna, sirf evidence likhna (kitni files, kitni der ka data).
"""
import glob
from collections import Counter
from pathlib import Path

import pandas as pd

from backend import config
from backend.model import AnomalyModel

DATA_DIR = Path(config.TRAIN_CSV).parent
LIVE_STEP = getattr(config, "LIVE_STEP", 5)


def stop_triggers(flags: list[bool]) -> tuple[int, int | None]:
    """(STOP kitni baar fire hota, pehla STOP kis window pe) - DecisionEngine jaisa rule."""
    run, fires, first = 0, 0, None
    for idx, flag in enumerate(flags):
        run = run + 1 if flag else 0
        if run == config.CONSECUTIVE_LIMIT:
            fires += 1
            first = idx if first is None else first
            run = 0
    return fires, first


def evaluate_file(model: AnomalyModel, path: Path) -> None:
    df = pd.read_csv(path)
    missing = [c for c in config.FEATURE_NAMES if c not in df.columns]
    if missing:
        print(f"{path.name}: columns missing {missing}")
        return
    df = df[config.FEATURE_NAMES].apply(pd.to_numeric, errors="coerce").dropna().reset_index(drop=True)
    res = model.predict_frame(df)

    n = max(len(res), 1)
    live = res.iloc[::LIVE_STEP]                       # live backend jitne windows judge karta
    fires, first = stop_triggers(live["is_anomaly"].tolist())
    top = Counter(res.loc[res["stats_flag"], "top_feature"]).most_common(2)
    top_txt = ", ".join(f"{name}({cnt})" for name, cnt in top) or "-"
    print(f"{path.name:24s} rows={len(res):5d}  IF={100 * res['if_flag'].sum() / n:5.1f}%  "
          f"stats={100 * res['stats_flag'].sum() / n:5.1f}%  combined={100 * res['is_anomaly'].sum() / n:5.1f}%  "
          f"STOP={fires}")
    print(f"{'':24s} stats me sabse zyada door feature: {top_txt}")


def main():
    if not Path(config.MODEL_PATH).exists():
        print("model.pkl nahi mila. Pehle python -m ml.train chalao.")
        return
    model = AnomalyModel()
    layers = "Isolation Forest + stats" if model.stats else "sirf Isolation Forest (stats.pkl nahi mila)"
    print(f"Layers: {layers} | live step {LIVE_STEP} | STOP = {config.CONSECUTIVE_LIMIT} lagatar anomalous windows\n")

    healthy = DATA_DIR / "healthy_test.csv"
    anomalies = sorted(Path(p) for p in glob.glob(str(DATA_DIR / "anomaly_*.csv")))

    print("--- Healthy held-out (expect: STOP = 0) ---")
    if healthy.exists():
        evaluate_file(model, healthy)
    else:
        print("healthy_test.csv nahi mili -> --step 1 --out ml/data/healthy_test.csv se collect karo")

    print("\n--- Induced safe anomalies (expect: STOP >= 1) ---")
    if anomalies:
        for p in anomalies:
            evaluate_file(model, p)
    else:
        print("anomaly_*.csv nahi mili -> --step 1 --out ml/data/anomaly_unbalance.csv se collect karo")


if __name__ == "__main__":
    main()
