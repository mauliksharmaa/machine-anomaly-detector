from __future__ import annotations
import requests

import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

import config
from backend_client import VIBRATION_AVAILABLE, get_events, get_feed, get_status
from status_logic import LIVE_STATES, STATES, derive_status, is_fault_reason

FAULT_EVENT_TYPES = ("ML_ANOMALY", "HARD_LIMIT")   # event types the backend writes for detected faults

feed = get_feed()
st.title("🛠️ Machine Health Monitor")
chart_window = st.sidebar.slider("Graph window (s)", 30, 300, 120, step=10)
st.sidebar.caption(f"Backend: {config.BACKEND_URL}")


def parse_ts(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone()   # SQLite gives naive UTC


def val(pkt, key, fmt, live):
    return fmt.format(pkt[key]) if live and pkt and pkt.get(key) is not None else "—"


def graph(df, col, title, now, live):
    st.caption(title)
    d = df[df["t"] >= now - chart_window][["t", col]].dropna()
    if d.empty:
        st.info("No data in this window yet.")
        return
    d = d.set_index(pd.to_datetime(d["t"], unit="s"))[[col]]
    if not live:   # extend to "now" with a gap so the lack of live data is visible
        d.loc[pd.to_datetime(now, unit="s")] = float("nan")
    st.line_chart(d, height=180)


@st.fragment(run_every=config.REFRESH_S)
def dashboard():
    now = time.time()
    pkt = feed.latest()
    status = get_status()
    age = now - pkt["_rx"] if pkt else None
    key = derive_status(pkt, age, feed.ws_connected, status is not None,
                        config.STALE_AFTER_S, now - feed.started_at)
    label, color, desc = STATES[key]
    live = key in LIVE_STATES

    # ---- A. status banner ----
    st.markdown(f"<div style='padding:14px 18px;border-radius:10px;background:{color};color:white'>"
                f"<div style='font-size:1.6rem;font-weight:700'>{label}</div>"
                f"<div style='opacity:.9'>{desc}</div></div>", unsafe_allow_html=True)
    st.write("")
    
    # ---- MOTOR CONTROLS ----
    st.subheader("Motor Control")

    motor_state = status.get("motor_state", "UNKNOWN") if status else "UNKNOWN"

    start_col, stop_col, state_col = st.columns([1, 1, 2])

    with start_col:
        if st.button(
            "▶ Start Motor",
            use_container_width=True,
            disabled=(
                status is None
                or motor_state == "RUNNING"
                or not live
            ),
        ):
            try:
                response = requests.post(
                    f"{config.BACKEND_URL}/api/start",
                    timeout=5,
                )
                response.raise_for_status()
                st.success("Start command sent to the motor.")
                st.rerun()
            except requests.RequestException as e:
                st.error(f"Could not start motor: {e}")

    with stop_col:
        if st.button(
            "⏹ Stop Motor",
            use_container_width=True,
            disabled=(
                status is None
                or motor_state != "RUNNING"
            ),
        ):
            try:
                response = requests.post(
                    f"{config.BACKEND_URL}/api/stop",
                    timeout=5,
                )
                response.raise_for_status()
                st.success("Stop command sent to the motor.")
                st.rerun()
            except requests.RequestException as e:
                st.error(f"Could not stop motor: {e}")

    with state_col:
        st.metric("Motor State", motor_state)

    if not live and pkt is not None:
        st.warning(f"Data is **not live** — last reading received {age:.0f} s ago "
                   f"(last known motor state: {pkt.get('motor_state')}). Values are hidden instead of "
                   "being shown as current.")
    if live and pkt.get("is_anomaly") and pkt.get("reasons"):
        st.error(f"Anomalous window: {pkt['reasons']}")
    if live and pkt.get("motor_state") == "STOPPED" and pkt.get("stop_reason"):
        (st.error if is_fault_reason(pkt["stop_reason"]) else st.info)(f"Motor stopped — {pkt['stop_reason']}")
    if status is not None and not status.get("model_loaded"):
        st.caption("⚠️ ML model not loaded on the backend — only hard limits are active.")

    # ---- B. metric cards ----
    c = st.columns(4)
    c[0].metric("Temperature", val(pkt, "temp", "{:.1f} °C", live))
    c[1].metric("Current", val(pkt, "i", "{:.3f} A", live))
    c[2].metric("Voltage", val(pkt, "v", "{:.2f} V", live))
    c[3].metric("Vibration (RMS accel)", val(pkt, "vibration", "{:.3f} m/s²", live),
                help="Backend's own 'vibration' feature (backend/processing.py): RMS of acceleration "
                     "after removing the per-axis mean, over the last 10 readings.")
    if pkt:
        st.caption(f"Last data received: {datetime.fromtimestamp(pkt['_rx']):%Y-%m-%d %H:%M:%S} "
                   f"({age:.1f} s ago)" + ("" if live else " — STALE"))
    else:
        st.caption("Last data received: never")
    if live and pkt.get("vibration") is None:
        st.caption("Vibration needs a full window of readings." if VIBRATION_AVAILABLE else
                   "Vibration unavailable: run Streamlit from the project root so `backend` can be imported.")

    # ---- D. health summary ----
    events, ev_err = get_events(500)
    recent_faults, latest = None, None
    if events is not None:
        cutoff = datetime.now().astimezone() - timedelta(hours=config.ANOMALY_COUNT_HOURS)
        recent_faults = sum(1 for e in events if e["event_type"] in FAULT_EVENT_TYPES and parse_ts(e["timestamp"]) >= cutoff)
        latest = events[0] if events else None

    consecutive = status["consecutive_anomalies"] if status else None
    if not live:
        health = "Unknown (no live data)"
    elif key == "ANOMALY":
        health = "Anomaly / fault"
    elif consecutive:
        health = f"Warning — {consecutive} anomalous window(s) in a row"
    else:
        health = "Normal"

    st.subheader("Machine health summary")
    s = st.columns(4)
    s[0].metric("Machine status", label)
    s[1].metric("Health (from backend)", health)
    s[2].metric(f"Fault events, last {config.ANOMALY_COUNT_HOURS} h",
                recent_faults if recent_faults is not None else "—",
                help="Count of ML_ANOMALY + HARD_LIMIT stop events from /api/events.")
    s[3].metric("Anomaly score", val(pkt, "score", "{:.3f}", live),
                help="Isolation Forest score from the backend; only present for evaluated windows while running.")
    if ev_err:
        st.caption(f"Could not load events: {ev_err}")
    elif latest:
        st.warning(f"**Latest event — {latest['event_type']}** · {parse_ts(latest['timestamp']):%Y-%m-%d %H:%M:%S}\n\n{latest['reason']}")
    else:
        st.success("No events recorded.")

    # ---- C. graphs ----
    st.subheader("Live graphs")
    hist = feed.snapshot()
    if not hist:
        st.info("No readings received yet.")
    else:
        df = pd.DataFrame(hist).rename(columns={"_rx": "t"})
        a, b = st.columns(2)
        with a:
            graph(df, "temp", "Temperature (°C)", now, live)
            graph(df, "v", "Voltage (V)", now, live)
        with b:
            graph(df, "i", "Current (A)", now, live)
            graph(df, "vibration", "Vibration (m/s², RMS)", now, live)
        st.caption(f"History is kept in memory only (last {config.HISTORY_LEN} readings) and resets when "
                   "the frontend restarts.")
    st.caption(f"Live stream: {'connected' if feed.ws_connected else 'disconnected'} ({feed.ws_url})"
               + (f" · {feed.last_error}" if feed.last_error and not feed.ws_connected else ""))


dashboard()
