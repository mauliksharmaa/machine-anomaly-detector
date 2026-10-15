from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from backend.database import get_events, save_event
from backend.schemas import EventOut

router = APIRouter(prefix="/api")


class ConnectionManager:
    def __init__(self):
        self.connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.add(ws)

    def disconnect(self, ws: WebSocket):
        self.connections.discard(ws)

    async def broadcast(self, data: dict):
        for ws in list(self.connections):
            try:
                await ws.send_json(data)
            except Exception:
                self.disconnect(ws)


manager = ConnectionManager()


@router.get("/status")
def status(request: Request):
    engine = request.app.state.engine
    return {
        "motor_state": engine.motor_state,
        "stop_reason": engine.stop_reason,
        "consecutive_anomalies": engine.consecutive,
        "model_loaded": request.app.state.model is not None,
    }


@router.get("/events", response_model=list[EventOut])
def events(limit: int = 50, event_type: str | None = None):
    """Motor STOP events (newest pehle). event_type: ML_ANOMALY, HARD_LIMIT, MANUAL_STOP, ESP32_STOP"""
    return get_events(min(limit, 500), event_type)


@router.post("/stop")
def stop(request: Request):
    state = request.app.state
    was_running = state.engine.motor_state == "RUNNING"
    state.engine.manual_stop()
    state.mqtt.publish_control("STOP")
    if was_running:
        save_event("MANUAL_STOP", "manual stop via API", recent_packets=list(state.windower.buf))
    return {"motor_state": "STOPPED"}


@router.post("/start")
def start(request: Request):
    state = request.app.state
    state.engine.start()
    state.windower.clear()          # purane window ka data hata do
    state.mqtt.publish_control("START")
    return {"motor_state": "RUNNING"}


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()   # client se kuch aaye to ignore, bas connection zinda rakho
    except WebSocketDisconnect:
        manager.disconnect(ws)
