"""Collect kiye healthy data ki quality check karta hai (train se pehle chalao).

Run (project root se):
    python -m ml.inspect_data
"""
import pandas as pd

from backend import config


def main():
    df = pd.read_csv(config.TRAIN_CSV)
    print(f"Rows: {len(df)}   (NaN rows: {df.isna().any(axis=1).sum()})")
    if len(df) < 500:
        print("-> Data kam hai. Kam se kam 1500-2000 rows (15-20 min) collect karo.\n")

    print("\nFeature summary:")
    print(df[config.FEATURE_NAMES].describe().T[["mean", "std", "min", "max"]].round(4))

    flat = [c for c in config.FEATURE_NAMES if df[c].std() < 1e-6]
    if flat:
        print(f"\nWarning: in features me koi variation nahi: {flat} (sensor connected hai?)")

    med = df["i_mean"].median()
    off_like = int((df["i_mean"] < 0.2 * med).sum())
    if off_like:
        print(f"\nWarning: {off_like} rows motor-band jaisi lag rahi hain (current bahut kam). "
              "Healthy RUNNING data me ye nahi honi chahiye, CSV se hata do.")

    print("\nObserved healthy maximums:")
    print(f"  temp_mean max : {df['temp_mean'].max():.2f}")
    print(f"  i_max max     : {df['i_max'].max():.4f}")
    print("Hard limits ke liye suggestion (config.py + firmware):")
    print(f"  MAX_TEMP    ~ {df['temp_mean'].max() + 15:.0f}")
    print(f"  MAX_CURRENT ~ {df['i_max'].max() * 1.5:.2f}")


if __name__ == "__main__":
    main()
