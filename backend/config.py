import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Units poore project me: temp degC, accel m/s^2, gyro rad/s, voltage V, current AMPERE

# .env file se settings load (DATABASE_URL waghera)
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

# ---------- MQTT ----------
MQTT_HOST = "localhost"          # laptop pe broker chal raha hai to localhost
MQTT_PORT = 1883
TOPIC_SENSORS = "machine/sensors"   # ESP32 -> backend
TOPIC_CONTROL = "machine/control"   # backend -> ESP32
TOPIC_STATUS = "machine/status"     # ESP32 -> backend (optional ack)

# ---------- Processing ----------
WINDOW_SIZE = 10                 # kitni readings ki window (10 readings ~ 1-2 sec)

# ---------- Decision ----------
CONSECUTIVE_LIMIT = 3            # lagatar itne anomalous windows -> STOP
MAX_TEMP = 100                  # hard safety limit (deg C)
MAX_CURRENT = 0.75              # hard safety limit in AMPERE (pehle 750 mA tha). ml.inspect_data ke suggestion se baad me set karo

# ---------- Paths ----------
# PostgreSQL: .env file me DATABASE_URL set karo (.env.example dekho).
# .env nahi hai to fallback SQLite (machine.db) use hoga.
DB_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'machine.db'}")
MODEL_PATH = BASE_DIR / "ml" / "model.pkl"
TRAIN_CSV = BASE_DIR / "ml" / "data" / "normal.csv"


# ---------- ML features (train + live dono me same order) ----------
FEATURE_NAMES = [
    "temp_mean",
    "vibration",
    "v_mean",
    "i_mean",
    "i_max",
    "i_std",
]
