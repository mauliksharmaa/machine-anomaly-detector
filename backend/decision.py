import logging

from backend import config
from backend.schemas import SensorPacket

log = logging.getLogger("decision")


class DecisionEngine:
    """Motor STOP karna hai ya nahi, ye yahan decide hota hai."""

    def __init__(self):
        self.consecutive = 0
        self.motor_state = "STOPPED"
        self.stop_reason: str | None = None

    def hard_limit_reason(self, p: SensorPacket) -> str | None:
        if p.temp > config.MAX_TEMP:
            return f"HARD LIMIT: temp {p.temp:.1f} > {config.MAX_TEMP}"
        if p.i > config.MAX_CURRENT:
            return f"HARD LIMIT: current {p.i:.3f} > {config.MAX_CURRENT}"
        return None

    def update(self, packet: SensorPacket, is_anomaly: bool, detail: str = "", evaluated: bool = True) -> str | None:
        
        if self.motor_state == "STOPPED":
            return None

        reason = self.hard_limit_reason(packet)
        if reason:
            return self._stop(reason)

        if evaluated:
            self.consecutive = self.consecutive + 1 if is_anomaly else 0
            if self.consecutive >= config.CONSECUTIVE_LIMIT:
                reason = f"ML anomaly x{self.consecutive}"
                return self._stop(f"{reason}: {detail}" if detail else reason)
        return None

    def _stop(self, reason: str) -> str:
        self.motor_state = "STOPPED"
        self.stop_reason = reason
        log.warning("MOTOR STOP -> %s", reason)
        return reason

    def manual_stop(self) -> None:
        self.motor_state = "STOPPED"
        self.stop_reason = "manual stop"

    def sync_stopped(self, reason: str) -> None:
        """ESP32 ne khud (ya command se) motor roka, uska status backend me mirror karo."""
        self.motor_state = "STOPPED"
        self.stop_reason = self.stop_reason or reason

    def start(self) -> None:
        self.motor_state = "RUNNING"
        self.stop_reason = None
        self.consecutive = 0
