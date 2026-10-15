"""Motor ke sensor data se feature rows collect karke CSV me save karta hai.

Run (project root se):
    python -m backend.collect_data --minutes 10                  # healthy data -> ml/data/normal.csv
    python -m backend.collect_data --minutes 3 --step 1 --out ml/data/healthy_test.csv
    python -m backend.collect_data --minutes 2 --step 1 --out ml/data/anomaly_load.csv

Sirf tab record karta hai jab ESP32 status "RUNNING" bheje, taaki motor-band
(current ~0) wale rows healthy data me na mil jayen. Motor chalane ke liye backend
chalu rakho aur POST /api/start karo. Startup ke pehle seconds (inrush current)
jaanbujhkar data me aate hain, kyunki live monitoring me bhi wahi aayenge.

NOTE: normal.csv me kabhi bhi anomaly wala data mat daalo. Anomaly tests ke liye
hamesha alag --out file use karo.
"""
import argparse
import logging
import time
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from backend import config
from backend.mqtt_client import MQTTService
from backend.processing import Windower
from backend.schemas import SensorPacket

logging.basicConfig(level=logging.INFO)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--step", type=int, default=2,
                    help="har kitni readings pe ek row (training: 2, evaluation files: 1)")
    ap.add_argument("--out", default=str(config.TRAIN_CSV), help="output CSV path")
    ap.add_argument("--ignore-status", action="store_true",
                    help="motor status check na kare, sab record kare (baad me inspect_data se check karna)")
    args = ap.parse_args()
    out_path = Path(args.out)

    rows: list[dict] = []
    windower = Windower(step=args.step)
    state = {"running": args.ignore_status, "dropped": 0}

    def on_status(text: str):
        running = text.strip().upper() == "RUNNING"
        if args.ignore_status:
            return
        if running and not state["running"]:
            windower.clear()          # motor start se fresh window (startup transient data me aayega)
            print(">> Motor RUNNING -> recording shuru")
        elif not running and state["running"]:
            print(">> Motor STOPPED -> recording pause")
        state["running"] = running

    def on_sensor(payload: dict):
        if not state["running"]:
            return
        try:
            packet = SensorPacket(**payload)
        except ValidationError:
            state["dropped"] += 1
            return
        features = windower.add(packet)
        if features:
            rows.append(features)

    svc = MQTTService(on_sensor, on_status, client_id="collector")
    svc.start()

    end = time.time() + args.minutes * 60
    print(f"Collecting up to {args.minutes} min -> {out_path}. Motor chalane ke liye POST /api/start karo.")
    try:
        while time.time() < end:
            time.sleep(5)
            print(f"  rows: {len(rows)} | motor running: {state['running']} | invalid packets: {state['dropped']}")
    except KeyboardInterrupt:
        print("Stopped early.")
    svc.stop()

    if state["dropped"] and not rows:
        print("Packets aa rahe hain par schemas.py se match nahi ho rahe -> ESP32 ka JSON format check karo.")
    if not rows:
        print("Koi row save nahi hui. Motor RUNNING status nahi aaya, ya data nahi aa raha.")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=config.FEATURE_NAMES)
    header = not out_path.exists()
    df.to_csv(out_path, mode="a", header=header, index=False)
    print(f"Saved {len(df)} rows -> {out_path}")


if __name__ == "__main__":
    main()
