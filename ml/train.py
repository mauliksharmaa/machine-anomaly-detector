"""normal.csv (sirf healthy data) pe dono layers train karta hai:
   1. Isolation Forest   -> ml/model.pkl   (primary ML)
   2. Stats layer        -> ml/stats.pkl   (z-score + Mahalanobis, "kyun" batane ke liye)

Run (project root se):
    python -m ml.train

Training me anomaly data use nahi hota (one-class): jo healthy jaisa nahi, wo anomaly.
Pehle single-sample glitch wali rows hataayi jaati hain (ek bura reading 10 lagatar windows
me dikhta hai), warna std/covariance phool jaate hain aur stats layer dheeli ho jaati hai.
"""
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from backend import config
from backend.stats_layer import STATS_PATH, StatsLayer

DATA_PATH = Path(config.TRAIN_CSV)
MODEL_PATH = Path(config.MODEL_PATH)
FEATURES = config.FEATURE_NAMES
GLITCH_Z = 8.0          # median/MAD se itna door = glitch row


def drop_glitch_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    med = df.median()
    mad = (df - med).abs().median() * 1.4826
    scale = np.maximum(mad, np.maximum(0.01 * med.abs(), 1e-6))   # near-constant feature pe phatne se bachao
    bad = ((df - med).abs() / scale > GLITCH_Z).any(axis=1)
    return df[~bad].reset_index(drop=True), int(bad.sum())


def drift_report(df: pd.DataFrame, stats: StatsLayer) -> None:
    """CSV time-order me hai. Shuru aur aakhri 1/3 hisse ka mean compare karo."""
    third = max(len(df) // 3, 1)
    first, last = df.iloc[:third], df.iloc[-third:]
    drifting = [(n, (last[n].mean() - first[n].mean()) / sd) for n, sd in zip(FEATURES, stats.std)]
    drifting = [(n, s) for n, s in drifting if abs(s) > 1.5]
    if drifting:
        print("\nWarning: ye features data ke dauran drift kar rahe hain (pehla vs aakhri 1/3):")
        for n, s in drifting:
            print(f"  {n}: {s:+.1f} std ka shift")
        print("  -> training me poora range (thanda start se garam steady-state) hona chahiye.")


def main():
    if not DATA_PATH.exists():
        print(f"Normal data file nahi mili: {DATA_PATH}")
        print("Pehle python -m backend.collect_data se healthy data collect karo.")
        return

    df = pd.read_csv(DATA_PATH)
    missing = [c for c in FEATURES if c not in df.columns]
    if missing:
        print("CSV mein required columns missing hain:", missing)
        print("CSV ke columns:", list(df.columns))
        print("backend/config.py ka FEATURE_NAMES aur CSV ka header same hona chahiye.")
        return

    df = df[FEATURES].apply(pd.to_numeric, errors="coerce").dropna().reset_index(drop=True)
    total = len(df)
    df, n_glitch = drop_glitch_rows(df)
    print(f"Rows in CSV: {total} | glitch rows hataayi: {n_glitch} ({100 * n_glitch / max(total, 1):.1f}%) | training rows: {len(df)}")
    if n_glitch > 0.2 * total:
        print("Warning: 20% se zyada rows glitch hain. Sensor/wiring noise check karo.")

    if len(df) < 200:
        print("200 se kam clean rows hain. Aur healthy data collect karo.")
        return

    # ---- Layer 1: Isolation Forest ----
    model = IsolationForest(n_estimators=200, contamination=0.01, random_state=42)
    model.fit(df)
    scores = model.decision_function(df)
    if_flagged = 100 * (model.predict(df) == -1).mean()
    joblib.dump(model, MODEL_PATH)

    # ---- Layer 2: statistics ----
    stats = StatsLayer.fit(df, FEATURES)
    _, maha, flag = stats.evaluate(df.to_numpy(float))
    stats.save(STATS_PATH)

    print(f"\n[Isolation Forest] training data me flagged: {if_flagged:.2f}%  (contamination=0.01 se ~1% expected, accuracy NAHI)")
    print("  score percentiles (1/5/50/95):", np.percentile(scores, [1, 5, 50, 95]).round(3))
    print(f"\n[Stats layer] Mahalanobis threshold {stats.maha_threshold:.2f} "
          f"(training max {maha.max():.2f}) | |z| limit {stats.z_limit} | training flagged {100 * flag.mean():.2f}%")
    print("  feature         mean       std(used)")
    for n, mu, sd, fl in zip(FEATURES, stats.mean, stats.std, stats.floored):
        print(f"  {n:12s} {mu:10.4f}  {sd:10.5f} {'(near-constant)' if fl else ''}")

    drift_report(df, stats)
    print(f"\nSaved: {MODEL_PATH.name}, {STATS_PATH.name}  -> ab backend restart karo.")


if __name__ == "__main__":
    main()
