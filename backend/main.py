import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from backend import config
from backend.api import manager, router
from backend.database import init_db, save_event
from backend.decision import DecisionEngine
from backend.model import AnomalyModel
from backend.mqtt_client import MQTTService
from backend.processing import Windower
from backend.schemas import SensorPacket

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
log = logging.getLogger("main")


def handle_sensor(payload: dict) -> None:
    """Har sensor packet ka poora pipeline (MQTT thread me chalta hai)."""
    state = app.state

    try:
        packet = SensorPacket(**payload)
    except ValidationError as e:
        log.warning("invalid packet dropped: %s", e.errors()[0])
        return

    score, is_anomaly, reasons, evaluated, detail = None, False, "", False, None
    features = state.windower.add(packet)
    # ML sirf tab jab motor RUNNING ho (band motor ke readings anomaly nahi hote)
    if features is not None and state.model is not None and state.engine.motor_state == "RUNNING":
        try:
            detail = state.model.predict_detail(features)
            score, is_anomaly = detail["score"], detail["is_anomaly"]
            reasons = "; ".join(detail["reasons"])
            evaluated = True
        except Exception:
            # ML fail ho to bhi hard limits chalne chahiye
            log.exception("model.predict failed; sirf hard limits use ho rahe hain")

    stop_reason = state.engine.update(packet, is_anomaly, reasons, evaluated)
    if stop_reason:
        state.mqtt.publish_control("STOP")
        # Sirf STOP par DB me ek event (aakhri 10 readings ke saath). Normal readings save nahi hote.
        event_type = "HARD_LIMIT" if stop_reason.startswith("HARD LIMIT") else "ML_ANOMALY"
        save_event(event_type, stop_reason, detail, features, list(state.windower.buf))

    event = {
        **packet.model_dump(),
        "score": score,
        "is_anomaly": is_anomaly,
        "reasons": reasons,
        "motor_state": state.engine.motor_state,
        "stop_reason": state.engine.stop_reason,
    }
    asyncio.run_coroutine_threadsafe(manager.broadcast(event), state.loop)


def handle_status(text: str) -> None:
    """ESP32 ka RUNNING/STOPPED status backend ke engine se sync karta hai."""
    log.info("ESP32 status: %s", text)
    status = text.strip().upper()
    engine = app.state.engine
    if status == "RUNNING" and engine.motor_state != "RUNNING":
        engine.start()
        app.state.windower.clear()
    elif status == "STOPPED" and engine.motor_state != "STOPPED":
        engine.sync_stopped("stopped by ESP32 (local failsafe/command)")
        save_event("ESP32_STOP", engine.stop_reason, recent_packets=list(app.state.windower.buf))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.loop = asyncio.get_running_loop()
    # Har LIVE_STEP-th reading pe window judge hoti hai. Ek glitch sample sirf WINDOW_SIZE/LIVE_STEP
    # windows me dikhta hai (10/5 = 2), isliye 3 lagatar windows wale rule se ek glitch STOP nahi karata.
    app.state.windower = Windower(step=getattr(config, "LIVE_STEP", 5))
    app.state.engine = DecisionEngine()

    try:
        app.state.model = AnomalyModel()
        log.info("ML model loaded")
    except FileNotFoundError:
        app.state.model = None
        log.warning("model.pkl nahi mila -> sirf hard limits kaam karenge. Pehle ml/train.py chalao.")

    app.state.mqtt = MQTTService(handle_sensor, handle_status)
    app.state.mqtt.start()
    yield
    app.state.mqtt.stop()


app = FastAPI(title="Machine Monitor", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
