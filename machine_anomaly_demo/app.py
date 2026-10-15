"""Portfolio-only Streamlit demo for the Machine Anomaly Detector project.
All values are illustrative/simulated. This app does not connect to hardware or a backend.
"""
import streamlit as st
import numpy as np
import pandas as pd

st.set_page_config(
    page_title="Machine Health Monitor | Demo",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🛠️ Machine Health Monitor")
st.caption("Portfolio preview · Simulated sensor data · No live hardware connection")

with st.sidebar:
    st.header("Demo controls")
    st.info("This is a visual demo. Readings and events below are simulated; motor controls are disabled.")
    view = st.radio("Page", ["Dashboard", "Recent Events"])
    st.divider()
    st.caption("Project stack: ESP32 · MQTT · FastAPI · Streamlit · Isolation Forest")

if view == "Dashboard":
    st.markdown(
        "<div style='padding:14px 18px;border-radius:10px;background:#475569;color:white'>"
        "<div style='font-size:1.5rem;font-weight:700'>DEMO MODE</div>"
        "<div>Illustrative values only — this page is not connected to an ESP32 or backend.</div></div>",
        unsafe_allow_html=True,
    )
    st.write("")
    st.subheader("Machine overview")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Temperature", "42.6 °C", "1.2 °C")
    m2.metric("Current", "0.842 A", "0.036 A")
    m3.metric("Voltage", "12.08 V", "−0.04 V")
    m4.metric("Vibration (RMS accel)", "0.184 m/s²", "0.021 m/s²")

    st.subheader("Machine health summary")
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Machine status", "Demo / Idle")
    h2.metric("Health status", "Illustrative normal")
    h3.metric("Fault events (24 h)", "2")
    h4.metric("Anomaly score", "0.173")

    st.subheader("Sensor trends")
    st.caption("Synthetic trend data for UI demonstration; not actual sensor measurements.")
    rng = np.random.default_rng(23)
    t = np.arange(60)
    trend = pd.DataFrame({
        "Sample": t,
        "Temperature (°C)": 41.5 + 0.035 * t + rng.normal(0, 0.35, len(t)),
        "Voltage (V)": 12.1 - 0.0015 * t + rng.normal(0, 0.025, len(t)),
        "Current (A)": 0.78 + 0.001 * t + rng.normal(0, 0.035, len(t)),
        "Vibration (m/s²)": 0.14 + 0.0007 * t + rng.normal(0, 0.012, len(t)),
    }).set_index("Sample")
    left, right = st.columns(2)
    with left:
        st.markdown("**Temperature**")
        st.line_chart(trend[["Temperature (°C)"]], height=210)
        st.markdown("**Current**")
        st.line_chart(trend[["Current (A)"]], height=210)
    with right:
        st.markdown("**Voltage**")
        st.line_chart(trend[["Voltage (V)"]], height=210)
        st.markdown("**Vibration**")
        st.line_chart(trend[["Vibration (m/s²)"]], height=210)

    st.subheader("Motor control")
    c1, c2, c3 = st.columns([1, 1, 2])
    c1.button("▶ Start Motor", disabled=True, use_container_width=True)
    c2.button("⏹ Stop Motor", disabled=True, use_container_width=True)
    c3.caption("Controls disabled in this public demo. No motor commands can be sent.")

    st.subheader("Recent event preview")
    st.warning("Illustrative event: ML_ANOMALY · Vibration exceeded the example threshold.")
    st.caption("The deployed portfolio demo is intentionally read-only and uses simulated data.")
else:
    st.subheader("🚨 Recent Events")
    st.caption("Example event history for interface preview only. These are not real recorded incidents.")
    events = pd.DataFrame([
        {"Time (demo)": "2026-10-15 14:32:08", "Type": "ML_ANOMALY", "Description": "Illustrative vibration anomaly detected", "IF score": 0.173},
        {"Time (demo)": "2026-10-15 13:47:51", "Type": "HARD_LIMIT", "Description": "Illustrative current threshold exceeded", "IF score": 0.091},
        {"Time (demo)": "2026-10-15 12:16:23", "Type": "MANUAL_STOP", "Description": "Example manual stop event", "IF score": None},
    ])
    st.dataframe(events, hide_index=True, use_container_width=True)
    st.info("Sample rows only. The live project records events through its backend API.")
