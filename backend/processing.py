import math
from collections import deque

import numpy as np

from backend import config
from backend.schemas import SensorPacket


def extract_features(window: list[SensorPacket]) -> dict[str, float]:
    temp = np.array([p.temp for p in window])

    ax = np.array([p.ax for p in window])
    ay = np.array([p.ay for p in window])
    az = np.array([p.az for p in window])

    # Overall vibration; gravity/axis offsets removed
    ax_vib = ax - ax.mean()
    ay_vib = ay - ay.mean()
    az_vib = az - az.mean()

    vibration = np.sqrt(
        np.mean(ax_vib**2 + ay_vib**2 + az_vib**2)
    )

    volt = np.array([p.v for p in window])
    curr = np.array([p.i for p in window])

    return {
        "temp_mean": float(temp.mean()),
        "vibration": float(vibration),
        "v_mean": float(volt.mean()),
        "i_mean": float(curr.mean()),
        "i_max": float(curr.max()),
        "i_std": float(curr.std()),
    }


class Windower:
    """Readings buffer karta hai aur window poori hone pe features deta hai.

    step=1 -> har naye reading pe features (live monitoring)
    step=5 -> har 5 readings pe (data collection, kam correlated rows)
    """

    def __init__(self, size: int = config.WINDOW_SIZE, step: int = 1):
        self.size = size
        self.step = step
        self.buf: deque[SensorPacket] = deque(maxlen=size)
        self._count = 0

    def add(self, packet: SensorPacket) -> dict[str, float] | None:
        self.buf.append(packet)
        self._count += 1
        if len(self.buf) < self.size:
            return None
        if self._count % self.step != 0:
            return None
        return extract_features(list(self.buf))

    def clear(self) -> None:
        self.buf.clear()
        self._count = 0
