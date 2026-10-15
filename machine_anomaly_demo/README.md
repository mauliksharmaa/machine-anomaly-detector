# Machine Health Monitor — Portfolio Demo

A read-only Streamlit UI preview for the Machine Anomaly Detector portfolio project.

**Important:** This demo intentionally uses simulated values. It does not connect to an ESP32, MQTT broker, backend API, database, or motor. Motor controls are disabled. The simulated data is labeled in the UI so viewers are not misled into thinking it is live telemetry.

## Run locally

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy to Streamlit Community Cloud

1. Create a **new public GitHub repository** for this demo (for example, `machine-anomaly-detector-demo`).
2. Upload `app.py`, `requirements.txt`, and this `README.md` to the repository root.
3. Open https://share.streamlit.io/ and sign in with GitHub.
4. Select **Create app**, choose the demo repository, branch `main`, and main file path `app.py`.
5. Deploy. After it builds, copy the public `https://....streamlit.app` URL.
6. Add that live demo URL to the README of your main `machine-anomaly-detector` repository and to your job applications if a demo link is accepted.

## Tech preview

- Streamlit dashboard layout and navigation
- Sensor metric cards and trend charts
- Example anomaly/event history
- Disabled, read-only motor controls

This is a portfolio UI demo, not a live monitoring or safety-control system.
