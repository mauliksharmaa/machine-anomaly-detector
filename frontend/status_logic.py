"""Maps what the existing backend reports onto the dashboard's status. No detection logic here.

The backend has no explicit "ESP32 connected" flag. The firmware publishes a reading every ~500 ms
even while the motor is stopped, so "readings still arriving" is the available connectivity signal.
Motor state, stop reason and the anomaly flag are used exactly as the backend reports them.
"""
from __future__ import annotations

# stop_reason prefixes written by backend/decision.py for system-detected faults.
FAULT_PREFIXES = ("ML anomaly", "HARD LIMIT")

STATES = {
    "RUNNING":      ("Connected / Running", "#16a34a", "ESP32 is sending data and the motor is running."),
    "IDLE":         ("Idle / Motor Off", "#2563eb", "ESP32 is connected and sending data; the motor is stopped."),
    "ANOMALY":      ("Anomaly Detected", "#dc2626", "The backend reports an anomaly."),
    "DISCONNECTED": ("Disconnected", "#6b7280", "No data from the ESP32. Values are NOT live."),
    "CONNECTING":   ("Waiting for data", "#d97706", "Waiting for the first reading."),
    "BACKEND_DOWN": ("Backend unreachable", "#6b7280", "Cannot reach the backend API / WebSocket."),
}
LIVE_STATES = ("RUNNING", "IDLE", "ANOMALY")


def is_fault_reason(reason: str | None) -> bool:
    return bool(reason) and reason.startswith(FAULT_PREFIXES)


def derive_status(pkt, age_s, ws_connected, rest_ok, stale_after_s, feed_age_s) -> str:
    if not ws_connected and not rest_ok:
        return "BACKEND_DOWN"
    if pkt is None:
        return "CONNECTING" if (ws_connected and feed_age_s < stale_after_s) else "DISCONNECTED"
    if age_s is None or age_s > stale_after_s:
        return "DISCONNECTED"
    motor = pkt.get("motor_state")
    if pkt.get("is_anomaly") or (motor == "STOPPED" and is_fault_reason(pkt.get("stop_reason"))):
        return "ANOMALY"
    return "RUNNING" if motor == "RUNNING" else "IDLE"
