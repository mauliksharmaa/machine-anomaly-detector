# Machine Anomaly Detector
### IoT-Based Machine Health Monitoring & Predictive Maintenance

An IoT and machine-learning project that monitors machine sensor readings, detects abnormal operating conditions, and sends motor-control commands when configured safety or anomaly conditions are triggered.

The system combines ESP32-based sensor acquisition, MQTT messaging, a FastAPI backend, an ML-based anomaly detection pipeline, database-backed event logging, and a real-time Streamlit dashboard.

> **Project status:** Designed for local development and hardware/simulator testing. Live hardware operation and production deployment should be validated in the target environment before use.

## Overview

Unexpected machine vibration, rising temperature, and abnormal electrical current can indicate developing faults. This project demonstrates how sensor data can be collected continuously, analyzed for unusual behavior, and presented through a dashboard for monitoring and investigation.

The system supports two types of protection:

- **Hard-limit checks:** Detect configured temperature and current limit violations.
- **ML-based anomaly detection:** Compare sensor-derived features against learned healthy operating behavior.

When a stop condition is triggered, the backend can publish a STOP command through MQTT and record the event for later review.

## Key Features

- **IoT sensor monitoring:** Collect temperature, acceleration, gyroscope, voltage, and current readings.
- **Real-time dashboard:** Display machine state, live sensor metrics, vibration, and recent fault events.
- **Machine-learning anomaly detection:** Use Isolation Forest alongside statistical analysis to identify unusual sensor patterns.
- **Safety-oriented decision logic:** Apply configurable hard limits and consecutive-anomaly rules.
- **MQTT communication:** Exchange sensor readings, machine status, and control commands.
- **REST API:** Access machine status, retrieve events, and request motor start/stop operations.
- **WebSocket updates:** Stream incoming sensor events to connected clients.
- **Database event history:** Store significant stop and fault events.
- **Hardware-independent testing:** Use a simulated ESP32 publisher to test the software pipeline without physical hardware.
- **Model training and evaluation tools:** Inspect healthy data, train the model, and evaluate it against separate test sessions.

## System Architecture

flowchart TD
    A[ESP32 + Sensors] -->|Sensor readings| B[MQTT Broker]
    B --> C[FastAPI Backend]
    C --> D[Feature Extraction]
    D --> E[Isolation Forest]
    D --> F[Statistical Analysis]
    E --> G[Decision Engine]
    F --> G
    G --> H[Hard Safety Limits]
    H --> I[STOP / Control Decision]
    I -->|MQTT command| B
    B -->|Control command| A
    C --> J[(Database)]
    C --> K[REST API + WebSocket]
    K --> L[Streamlit Dashboard]


### Data flow

1. The ESP32 reads sensor measurements and publishes them to the MQTT broker.
2. The backend validates incoming packets and computes features from a rolling sensor window.
3. The anomaly detection model and statistical layer evaluate the features while the motor is running.
4. The decision engine combines anomaly results with configured safety limits.
5. When a stop condition is met, the backend publishes a control command and records a relevant event.
6. The dashboard displays machine status, sensor values, and recent events.

## Technology Stack

| Component | Technology |
|---|---|
| Firmware | ESP32, Arduino/C++ |
| Sensors | MPU6050-based accelerometer and gyroscope |
| Messaging | MQTT, Mosquitto, Paho MQTT |
| Backend | Python, FastAPI, Uvicorn |
| ML | scikit-learn, Isolation Forest |
| Statistical analysis | Feature statistics and Mahalanobis-distance-based analysis |
| Dashboard | Streamlit, Pandas |
| API communication | REST, WebSocket |
| Database | SQLAlchemy, SQLite fallback or PostgreSQL |
| Model storage | Joblib / serialized model artifacts |

## Repository Structure

machine-anomaly-detector/
├── backend/
│   ├── api.py
│   ├── collect_data.py
│   ├── config.py
│   ├── database.py
│   ├── decision.py
│   ├── main.py
│   ├── model.py
│   ├── mqtt_client.py
│   ├── processing.py
│   ├── schemas.py
│   ├── stats_layer.py
│   ├── requirements.txt
│   └── README.md
├── frontend/
│   ├── app.py
│   ├── backend_client.py
│   ├── config.py
│   ├── dashboard.py
│   ├── events_page.py
│   ├── status_logic.py
│   ├── requirements.txt
│   └── README.md
├── hardware_test/
│   └── hardware_test.ino
├── machine_firmware/
│   ├── machine_firmware.ino
│   └── secrets_example.h
├── ml/
│   ├── data/
│   │   └── normal.csv
│   ├── model.pkl
│   ├── stats.pkl
│   ├── train.py
│   ├── evaluate.py
│   └── inspect_data.py
├── fake_esp32.py
├── .env.example
├── .gitignore
└── README.md

**Note:** `machine_firmware/secrets.h` is intentionally excluded from version control. Create it locally using your own Wi-Fi configuration and the example header as a reference.

## Prerequisites

For the local development setup, install:

- Python 3.10 or newer, compatible with the dependencies in the requirements files.
- Git.
- Mosquitto MQTT broker.
- PostgreSQL if you want to use PostgreSQL instead of the SQLite fallback.
- Arduino IDE and ESP32 board support for physical hardware testing.

A physical ESP32 and compatible sensor/motor hardware are needed for real sensor readings and hardware control. The software simulator can be used for an initial software-only test.


## Machine Learning Pipeline

### Feature extraction

The backend evaluates derived features from rolling sensor readings. The current model configuration uses:

- `temp_mean` — mean temperature.
- `vibration` — acceleration-based vibration feature.
- `v_mean` — mean voltage.
- `i_mean` — mean current.
- `i_max` — maximum current.
- `i_std` — current variability.

Maintain consistent feature names, ordering, and physical units between training and live inference.

### Anomaly detection

The ML pipeline combines two complementary approaches:

1. **Isolation Forest:** Learns patterns in healthy operating data and identifies readings that differ from those patterns.
2. **Statistical analysis:** Uses feature statistics and multivariate distance to help identify unusual behavior and explain contributing features.

The decision engine combines the evaluated anomaly flags with configurable hard safety limits and a consecutive-anomaly rule.

An anomaly score or flag is not, by itself, proof of a physical fault. Performance depends on representative training data, sensor quality, thresholds, and validation.

### Train the model

The project includes model-training and data-inspection scripts.

Inspect the healthy dataset:


The training process reads `ml/data/normal.csv` and generates or updates model artifacts, including `ml/model.pkl` and `ml/stats.pkl`.

Use representative healthy-operation data and inspect its quality before training. If you retrain the model, restart the backend so the new artifacts are loaded.

### Evaluate the model

The evaluation script can use a separate healthy test session and files matching `ml/data/anomaly_*.csv`. Collect and label test data independently from the training data.

Do not claim a particular accuracy, false-positive rate, or detection rate unless you have measured it on an appropriate, independent dataset.

## MQTT Topics

| Topic | Direction | Purpose |
|---|---|---|
| `machine/sensors` | ESP32 → backend | Sensor readings encoded as JSON |
| `machine/control` | Backend → ESP32 | Motor control commands |
| `machine/status` | ESP32 → backend | Reported machine state |

Example sensor message:

```json
{
  "temp": 34.2,
  "ax": 0.1,
  "ay": 0.0,
  "az": 9.8,
  "v": 5.0,
  "i": 0.32
}


The firmware and backend must agree on topic names, payload format, and measurement units.

## REST API

The backend exposes the following endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/status` | Current backend motor state, stop reason, anomaly counter, and model-loaded status |
| `GET` | `/api/events` | Retrieve recent recorded events |
| `POST` | `/api/start` | Request a motor start through the backend |
| `POST` | `/api/stop` | Request a motor stop through the backend |
| `WS` | `/api/ws` | Receive real-time sensor updates |


The API endpoints are not an authentication system. Keep the development API on a trusted local interface unless you have implemented appropriate authentication, authorization, and network security.

## Database and Event Logging

The backend uses SQLAlchemy and supports a local SQLite fallback or a configured PostgreSQL database.

Significant stop events can include categories such as:

- `ML_ANOMALY`
- `HARD_LIMIT`
- `MANUAL_STOP`
- `ESP32_STOP`

The events endpoint returns recent records and supports filtering by event type. Normal sensor readings are streamed to the frontend; the database is primarily used for event history rather than storing every incoming reading.

## Safety and Security Considerations

- Never commit `.env`, `secrets.h`, passwords, access tokens, or private keys.
- Keep example configuration files limited to placeholders.
- Do not expose an unauthenticated MQTT broker or unrestricted control API to the public internet.
- Validate thresholds against the actual motor, sensor range, and operating conditions.
- Test stop behavior and sensor-failure handling with the motor safely disconnected or otherwise made safe before hardware trials.
- The software stop command should not be treated as a substitute for independent physical safety controls.
- Review all firmware, wiring, motor-driver limits, and emergency-stop requirements before connecting real equipment.

## Current Limitations

- The default MQTT and frontend settings are intended for local development.
- Simulator data does not establish real-world detection performance.
- Model behavior depends on the quality and representativeness of healthy training data.
- Remote deployment requires network, broker, database, and security configuration beyond simply publishing the source code.
- Production readiness requires additional validation, access controls, monitoring, and hardware safety testing.

## Future Improvements

Potential improvements include authenticated MQTT communication, secure remote deployment, improved sensor calibration, broader fault datasets, automated evaluation reports, model-version tracking, and stronger API access controls.

## Author

**Maulik Sharma**

GitHub: [@mauliksharmaa](https://github.com/mauliksharmaa)
