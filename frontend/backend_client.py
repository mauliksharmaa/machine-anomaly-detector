"""Access to the EXISTING backend. Nothing here re-implements backend logic.

Interfaces used (read from backend/api.py, main.py, schemas.py, processing.py):
  * WS  /api/ws      one JSON message per ESP32 packet: temp, ax, ay, az, gx, gy, gz, v, i,
                     score, is_anomaly, reasons, motor_state, stop_reason   (no timestamp, no vibration)
  * GET /api/status  motor_state, stop_reason, consecutive_anomalies, model_loaded
  * GET /api/events  ?limit=&event_type=  -> newest first (EventOut)
Vibration is NOT broadcast by the backend; it is only computed inside backend.processing.extract_features.
We import and call that same function on the last WINDOW_SIZE live packets (no new formula).
"""
from __future__ import annotations

import json
import threading
import time
from collections import deque

import requests
import streamlit as st
import websocket  # websocket-client

import config

try:  # reuse backend's own code
    from backend.config import WINDOW_SIZE
    from backend.processing import extract_features
    from backend.schemas import SensorPacket
    VIBRATION_AVAILABLE = True
except Exception:  # noqa: BLE001  (e.g. not started from the project / deps missing)
    VIBRATION_AVAILABLE = False


class LiveFeed:
    """Single background WebSocket consumer shared by all sessions (one connection, bounded memory)."""

    def __init__(self, base_url: str):
        self.ws_url = base_url.replace("https://", "wss://").replace("http://", "ws://") + "/api/ws"
        self.lock = threading.Lock()
        self.history: deque[dict] = deque(maxlen=config.HISTORY_LEN)
        self._window: deque = deque(maxlen=WINDOW_SIZE if VIBRATION_AVAILABLE else 1)
        self._last_motor = None
        self.ws_connected = False
        self.last_error: str | None = None
        self.started_at = time.time()
        threading.Thread(target=self._run, daemon=True, name="live-feed").start()

    def _vibration(self, pkt: dict) -> float | None:
        if not VIBRATION_AVAILABLE:
            return None
        try:
            if pkt.get("motor_state") != self._last_motor:   # backend clears its window on start
                self._window.clear()
                self._last_motor = pkt.get("motor_state")
            self._window.append(SensorPacket(**pkt))
            if len(self._window) < WINDOW_SIZE:
                return None
            return extract_features(list(self._window))["vibration"]
        except Exception:  # noqa: BLE001
            return None

    def _run(self) -> None:
        def on_open(ws):
            self.ws_connected, self.last_error = True, None

        def on_message(ws, message):
            try:
                pkt = json.loads(message)
            except ValueError:
                return
            pkt["_rx"] = time.time()
            pkt["vibration"] = self._vibration(pkt)
            with self.lock:
                self.history.append(pkt)

        def on_close(ws, *_):
            self.ws_connected = False

        def on_error(ws, err):
            self.ws_connected, self.last_error = False, str(err)

        while True:  # auto-reconnect
            try:
                websocket.WebSocketApp(self.ws_url, on_open=on_open, on_message=on_message,
                                       on_close=on_close, on_error=on_error
                                       ).run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:  # noqa: BLE001
                self.last_error = str(e)
            self.ws_connected = False
            time.sleep(2)

    def latest(self) -> dict | None:
        with self.lock:
            return dict(self.history[-1]) if self.history else None

    def snapshot(self) -> list[dict]:
        with self.lock:
            return list(self.history)


@st.cache_resource(show_spinner=False)
def get_feed() -> LiveFeed:
    return LiveFeed(config.BACKEND_URL)


# Cached REST helpers: they raise on failure (Streamlit does not cache exceptions).
@st.cache_data(ttl=2, show_spinner=False)
def _status() -> dict:
    r = requests.get(f"{config.BACKEND_URL}/api/status", timeout=2)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=5, show_spinner=False)
def _events(limit: int) -> list[dict]:
    r = requests.get(f"{config.BACKEND_URL}/api/events", params={"limit": limit}, timeout=5)
    r.raise_for_status()
    return r.json()


def get_status() -> dict | None:
    try:
        return _status()
    except Exception:  # noqa: BLE001
        return None


def get_events(limit: int = 100) -> tuple[list[dict] | None, str | None]:
    """Returns (events, error). One query serves both pages; filtering is done client-side."""
    try:
        return _events(limit), None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def refresh_events() -> None:
    _events.clear()
