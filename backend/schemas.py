from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

G = 9.80665

# Purane firmware ke key names -> (naya key, multiplier canonical unit me badalne ke liye)
LEGACY_KEYS = {
    "mpu_temp_C": ("temp", 1.0),
    "ax_g": ("ax", G),
    "ay_g": ("ay", G),
    "az_g": ("az", G),
    "voltage_V": ("v", 1.0),
    "current_mA": ("i", 0.001),
}


def normalize_payload(data):
    """Purane format ko canonical format me badalta hai.

    Canonical units: temp = deg C, accel = m/s^2, gyro = rad/s, v = Volt, i = AMPERE.
    machine_firmware.ino already isi format me bhejta hai.
    """
    if not isinstance(data, dict):
        return data
    out = dict(data)
    for old, (new, scale) in LEGACY_KEYS.items():
        if old in out and new not in out:
            out[new] = float(out.pop(old)) * scale
    return out


class SensorPacket(BaseModel):
    """ESP32 se aane wala sensor data (canonical units, upar dekho)."""

    model_config = ConfigDict(allow_inf_nan=False)   # NaN/inf packet reject

    temp: float
    ax: float
    ay: float
    az: float

    # Agar firmware gyro nahi bhejta to 0 rahega (gyro_rms feature tab useless hoga).
    gx: float = 0.0
    gy: float = 0.0
    gz: float = 0.0

    v: float
    i: float

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy(cls, data):
        return normalize_payload(data)


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    event_type: str
    reason: str
    if_score: float | None
    maha: float | None
    features: dict | None
    z_scores: dict | None
    recent_readings: list | None
