"""Frontend configuration. Override with environment variables (PowerShell: $env:BACKEND_URL="...")."""
import os
import sys
from pathlib import Path

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
STALE_AFTER_S = float(os.getenv("STALE_AFTER_S", "5"))   # ESP32 sends every ~0.5 s
REFRESH_S = float(os.getenv("REFRESH_S", "1"))           # dashboard refresh period
HISTORY_LEN = 600                                        # bounded in-memory history (~5 min)
ANOMALY_COUNT_HOURS = 24                                 # window for "recent anomaly count"

# Make the existing `backend` package importable (frontend/ lives next to backend/) so the
# backend's own vibration calculation can be reused instead of re-implemented.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
