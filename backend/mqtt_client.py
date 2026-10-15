import json
import logging
from typing import Callable

import paho.mqtt.client as mqtt

from backend import config

log = logging.getLogger("mqtt")


class MQTTService:
    def __init__(
        self,
        on_sensor: Callable[[dict], None],
        on_status: Callable[[str], None] | None = None,
        client_id: str = "machine-backend",
    ):
        self.on_sensor = on_sensor
        self.on_status = on_status
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def start(self) -> None:
        # connect_async: broker abhi band ho to bhi app start hoga, baad me auto-reconnect
        self.client.connect_async(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def publish_control(self, cmd: str) -> None:
        payload = json.dumps({"cmd": cmd})
        self.client.publish(config.TOPIC_CONTROL, payload, qos=1)
        log.info("control -> %s", payload)

    # ---------- callbacks (MQTT thread me chalte hain) ----------
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        log.info("MQTT connected (%s)", reason_code)
        client.subscribe([(config.TOPIC_SENSORS, 0), (config.TOPIC_STATUS, 1)])

    def _on_message(self, client, userdata, msg):
        text = msg.payload.decode(errors="ignore")
        if msg.topic == config.TOPIC_SENSORS:
            try:
                self.on_sensor(json.loads(text))
            except json.JSONDecodeError:
                log.warning("bad JSON: %s", text)
        elif msg.topic == config.TOPIC_STATUS and self.on_status:
            self.on_status(text)
