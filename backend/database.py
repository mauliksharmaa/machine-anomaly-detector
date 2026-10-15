import logging
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, JSON, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from backend import config

log = logging.getLogger("database")

# check_same_thread sirf SQLite ke liye hai (MQTT thread + API thread dono DB use karte hain)
_connect_args = {"check_same_thread": False} if config.DB_URL.startswith("sqlite") else {}
engine = create_engine(config.DB_URL, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class AnomalyEvent(Base):
    """Har baar jab motor ruki: ek row. Normal running readings DB me save nahi hote."""

    __tablename__ = "anomaly_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    # ML_ANOMALY | HARD_LIMIT | MANUAL_STOP | ESP32_STOP
    event_type: Mapped[str] = mapped_column(String(20), index=True)
    reason: Mapped[str] = mapped_column(Text)
    if_score: Mapped[float | None] = mapped_column(Float, nullable=True)      # Isolation Forest score
    maha: Mapped[float | None] = mapped_column(Float, nullable=True)          # Mahalanobis distance
    features: Mapped[dict | None] = mapped_column(JSON, nullable=True)        # trigger window ke 6 features
    z_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)        # har feature ka z-score
    recent_readings: Mapped[list | None] = mapped_column(JSON, nullable=True)  # STOP se pehle ke aakhri <=10 raw readings


def init_db() -> None:
    Base.metadata.create_all(engine)


def save_event(event_type, reason, detail=None, features=None, recent_packets=None):
    """STOP event save karta hai. DB error aaye to bhi pipeline nahi rukta (sirf log hota hai).

    detail: model.predict_detail() ka dict (ya None)
    features: trigger window ke features (ya None)
    recent_packets: windower.buf ke SensorPacket objects (aakhri 10 tak)
    """
    try:
        recent = [p.model_dump() for p in list(recent_packets or [])[-10:]] or None
        row = AnomalyEvent(
            event_type=event_type,
            reason=reason,
            if_score=float(detail["score"]) if detail and detail.get("score") is not None else None,
            maha=float(detail["maha"]) if detail and detail.get("maha") is not None else None,
            features={k: float(v) for k, v in features.items()} if features else None,
            z_scores={k: float(v) for k, v in detail["z"].items()} if detail and detail.get("z") else None,
            recent_readings=recent,
        )
        with SessionLocal() as session:
            session.add(row)
            session.commit()
        return row
    except Exception:
        log.exception("anomaly event DB me save nahi hua (motor STOP phir bhi ho chuka hai)")
        return None


def get_events(limit: int = 50, event_type: str | None = None) -> list[AnomalyEvent]:
    stmt = select(AnomalyEvent)
    if event_type:
        stmt = stmt.where(AnomalyEvent.event_type == event_type)
    stmt = stmt.order_by(AnomalyEvent.id.desc()).limit(limit)
    with SessionLocal() as session:
        return list(session.scalars(stmt))
