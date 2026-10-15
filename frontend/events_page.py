"""Page 2: Recent Events (from GET /api/events)."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from backend_client import get_events, refresh_events

# The backend stores NO severity field. This is only a visual grouping of the existing event_type values.
CATEGORY = {
    "HARD_LIMIT":  ("🔴", "Fault – hard limit"),
    "ML_ANOMALY":  ("🔴", "Fault – ML anomaly"),
    "ESP32_STOP":  ("🟠", "Device stop"),
    "MANUAL_STOP": ("🔵", "Manual stop"),
}
FEATURE_COLS = ["temp_mean", "vibration", "v_mean", "i_mean", "i_max", "i_std"]


def parse_ts(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone()


st.title("🚨 Recent Events")
st.caption("Motor STOP events recorded by the backend (newest first). The backend does not store a severity "
           "level, so the colour marks the event type only.")

top = st.columns([1, 1, 1, 3])
limit = top[0].selectbox("Load last", [50, 100, 200, 500], index=1)
if top[1].button("🔄 Refresh"):
    refresh_events()

with st.spinner("Loading events…"):
    events, err = get_events(limit)

if err:
    st.error(f"Could not load events from the backend: {err}")
    st.stop()
if not events:
    st.info("No events recorded yet.")
    st.stop()

rows = []
for e in events:
    icon, cat = CATEGORY.get(e["event_type"], ("⚪", e["event_type"]))
    f = e.get("features") or {}
    rows.append({"Time": parse_ts(e["timestamp"]), "Type": f"{icon} {e['event_type']}", "type_raw": e["event_type"],
                 "Description": e["reason"],
                 **{k: f.get(k) for k in FEATURE_COLS}, "IF score": e.get("if_score"), "Mahalanobis": e.get("maha"),
                 "_ev": e})
df = pd.DataFrame(rows)

# ---- filters (client-side on the fetched rows) ----
fc = st.columns(2)
types = sorted(df["type_raw"].unique())
sel_types = fc[0].multiselect("Event type", types, default=types)
dmin, dmax = df["Time"].min().date(), df["Time"].max().date()
rng = fc[1].date_input("Date range", (dmin, dmax), min_value=dmin, max_value=dmax)
if isinstance(rng, tuple) and len(rng) == 2:
    df = df[(df["Time"].dt.date >= rng[0]) & (df["Time"].dt.date <= rng[1])]
df = df[df["type_raw"].isin(sel_types)]

if df.empty:
    st.info("No events match the current filters.")
    st.stop()

st.write(f"**{len(df)}** event(s)")
show = df.drop(columns=["type_raw", "_ev"]).reset_index(drop=True)
sel = st.dataframe(
    show, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row",
    column_config={"Time": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm:ss"),
                   "Description": st.column_config.TextColumn(width="large")},
)

# ---- details of the selected event ----
idx = sel.selection.rows[0] if sel and sel.selection.rows else 0
ev = df.reset_index(drop=True).loc[idx, "_ev"]
st.subheader(f"Event details — {ev['event_type']} · {parse_ts(ev['timestamp']):%Y-%m-%d %H:%M:%S}")
st.write(ev["reason"])
d1, d2 = st.columns(2)
with d1:
    if ev.get("features"):
        st.caption("Trigger-window features")
        st.dataframe(pd.DataFrame([ev["features"]]), hide_index=True)
    if ev.get("z_scores"):
        st.caption("Z-scores")
        st.dataframe(pd.DataFrame([ev["z_scores"]]), hide_index=True)
with d2:
    if ev.get("recent_readings"):
        st.caption("Last raw readings before the stop")
        st.dataframe(pd.DataFrame(ev["recent_readings"]), hide_index=True)
if not (ev.get("features") or ev.get("recent_readings")):
    st.caption("No sensor values were stored with this event.")
