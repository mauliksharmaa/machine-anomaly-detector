# Machine Health Monitor – Run Guide (Windows)

Sab commands **project root** (`mini_project` folder, jisme `backend`, `ml`, `.env` hai) se chalao.

## Units (poore project me same)
temp = °C, accel = m/s², gyro = rad/s, voltage = V, **current = Ampere**.
`machine_firmware.ino` isi format me bhejta hai. `backend/config.py` ke `MAX_CURRENT` bhi Ampere me hai.

## 1. One-time setup
```
python -m venv venv
venv\Scripts\activate
pip install -r backend\requirements.txt
```

**PostgreSQL:** service chalu ho, aur database `mini_project_data` bana ho (pgAdmin se ya `CREATE DATABASE mini_project_data;`).
Project root me `.env` file:
```
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/mini_project_data
```
Check: `python -c "from backend.database import init_db; init_db(); print('DB OK')"`

**Mosquitto (MQTT broker):** install karo, phir `C:\Program Files\mosquitto\mosquitto.conf` (Notepad as Administrator) me ye 2 lines add karo:
```
listener 1883 0.0.0.0
allow_anonymous true
```
Administrator PowerShell me firewall allow karo:
```
New-NetFirewallRule -DisplayName "Mosquitto 1883" -Direction Inbound -Protocol TCP -LocalPort 1883 -Action Allow
```

**ESP32:** `machine_firmware\machine_firmware.ino` me `WIFI_SSID`, `WIFI_PASS` aur `MQTT_HOST` badlo. `MQTT_HOST` = laptop ka IPv4 (`ipconfig` me "IPv4 Address"). Hotspot/WiFi badalne par IP badal sakta hai, to har baar check karo. ESP32 sirf 2.4 GHz WiFi use karta hai.

## 2. Roz ka run order
1. Mosquitto start: `"C:\Program Files\mosquitto\mosquitto.exe" -c "C:\Program Files\mosquitto\mosquitto.conf" -v`
2. (Optional check) naye terminal me: `"C:\Program Files\mosquitto\mosquitto_sub.exe" -t "machine/#" -v` — ESP32 ke packets dikhne chahiye.
3. Backend: `uvicorn backend.main:app --host 0.0.0.0 --port 8000` → http://localhost:8000/docs
4. ESP32 power on. Motor boot pe **band** rehta hai. Chalane ke liye `/docs` me `POST /api/start`.
5. Rokne ke liye `POST /api/stop`.

## 3. ML: healthy data -> train -> test (pehli baar)
Pehle `ml\model.pkl` delete/rename kar do (purana model collection ke beech motor na roke).

1. Healthy data (3 sessions, har ek 10 min, ESP32 reboot karke):
   `python -m backend.collect_data --minutes 10` → `POST /api/start` → motor ko chhedo mat.
2. Check: `python -m ml.inspect_data`
3. Train: `python -m ml.train`
4. Held-out healthy test (alag session): `python -m backend.collect_data --minutes 3 --step 1 --out ml\data\healthy_test.csv`
5. Safe anomaly test (ek-ek karke, alag file): `python -m backend.collect_data --minutes 2 --step 1 --out ml\data\anomaly_load.csv`
   aur anomaly isi dauran banao (jaise shaft pe halka brake/load; motor ko garam mat karo).
6. Evaluate: `python -m ml.evaluate`
7. Backend **restart** karo (model sirf startup pe load hota hai).

## 4. API
`GET /api/status`, `GET /api/events?limit=50&event_type=ML_ANOMALY` (STOP events, newest pehle), `POST /api/start`, `POST /api/stop`, `WS /api/ws`

## MQTT
| Topic | Direction | Payload |
|---|---|---|
| `machine/sensors` | ESP32 → backend | `{"temp":34.2,"ax":0.1,"ay":0.0,"az":9.8,"gx":0.0,"gy":0.0,"gz":0.0,"v":5.0,"i":0.32}` |
| `machine/control` | backend → ESP32 | `{"cmd":"STOP"}` / `{"cmd":"START"}` |
| `machine/status` | ESP32 → backend | `RUNNING` / `STOPPED` (retained) |
