from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .models import Side


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso(dt: datetime | None) -> str:
    value = as_utc(dt)
    return value.isoformat() if value else ""


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    return as_utc(dt)


def display_dt(dt: datetime | None, tz: ZoneInfo) -> str:
    value = as_utc(dt)
    if value is None:
        return ""
    return value.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")


def pips_from_prices(side: str, entry: float, exit_price: float, pip_size: float) -> float:
    if not pip_size:
        return 0.0
    if side == Side.BUY.value:
        return round((exit_price - entry) / pip_size, 1)
    return round((entry - exit_price) / pip_size, 1)


def safety_levels(side: str, entry: float, pips: float, pip_size: float) -> tuple[float, float]:
    delta = pips * pip_size
    if side == Side.BUY.value:
        return entry - delta, entry + delta
    return entry + delta, entry - delta
