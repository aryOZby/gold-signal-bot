from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .models import ParsedSignal, Side


@dataclass
class RiskSettings:
    """All risk controls are opt-in: the defaults reproduce the original behaviour."""

    # "fixed" = use the per-group lot. "risk_percent" = size from balance and SL distance.
    lot_mode: str = "fixed"
    # Percent of balance risked per signal, split evenly across its TP legs.
    risk_percent: float = 1.0
    min_lot: float = 0.01
    max_lot: float = 1.0
    lot_step: float = 0.01
    # Account-currency value of a 1.0 price move for 1 lot, used when the broker
    # can't report it. Standard XAUUSD contract = 100 oz.
    contract_value: float = 100.0

    # Reject malformed signals (SL/TP on the wrong side, SL already hit, etc.).
    sanity_checks: bool = False
    # 0 = no limit. Maximum SL distance from entry, in pips.
    max_sl_pips: float = 0.0

    # Stop opening new signals once today's realised loss reaches the limit.
    # Either value may be used; 0 = off. Open positions are never touched.
    daily_loss_limit: float = 0.0
    daily_loss_limit_percent: float = 0.0

    @property
    def uses_risk_percent(self) -> bool:
        return self.lot_mode.strip().lower() == "risk_percent"


def parse_risk_settings(raw: Optional[dict]) -> RiskSettings:
    raw = raw or {}
    defaults = RiskSettings()
    mode = str(raw.get("lot_mode") or defaults.lot_mode).strip().lower()
    if mode not in {"fixed", "risk_percent"}:
        raise ValueError(f"risk.lot_mode must be 'fixed' or 'risk_percent', got {mode!r}")

    def num(key: str) -> float:
        value = raw.get(key)
        return float(getattr(defaults, key) if value is None else value)

    settings = RiskSettings(
        lot_mode=mode,
        risk_percent=num("risk_percent"),
        min_lot=num("min_lot"),
        max_lot=num("max_lot"),
        lot_step=num("lot_step"),
        contract_value=num("contract_value"),
        sanity_checks=bool(raw.get("sanity_checks", defaults.sanity_checks)),
        max_sl_pips=max(0.0, num("max_sl_pips")),
        daily_loss_limit=abs(num("daily_loss_limit")),
        daily_loss_limit_percent=abs(num("daily_loss_limit_percent")),
    )
    if settings.uses_risk_percent:
        if not 0 < settings.risk_percent <= 10:
            raise ValueError("risk.risk_percent must be between 0 and 10")
        if settings.lot_step <= 0 or settings.min_lot <= 0 or settings.max_lot < settings.min_lot:
            raise ValueError("risk lot limits must satisfy 0 < min_lot <= max_lot and lot_step > 0")
    return settings


def validate_signal(
    signal: ParsedSignal,
    market_price: Optional[float] = None,
    max_sl_pips: float = 0.0,
    pip_size: float = 0.1,
) -> Optional[str]:
    """Return a rejection reason, or None if the signal is internally consistent."""
    entry = market_price if market_price else (signal.zone_low + signal.zone_high) / 2.0
    buy = signal.side == Side.BUY

    if buy and signal.sl >= signal.zone_low:
        return "sl_wrong_side"
    if not buy and signal.sl <= signal.zone_high:
        return "sl_wrong_side"
    for tp in signal.tps:
        if buy and tp <= signal.zone_low:
            return "tp_wrong_side"
        if not buy and tp >= signal.zone_high:
            return "tp_wrong_side"

    if market_price:
        if buy and market_price <= signal.sl:
            return "sl_already_hit"
        if not buy and market_price >= signal.sl:
            return "sl_already_hit"

    if max_sl_pips > 0 and pip_size > 0:
        distance = abs(entry - signal.sl) / pip_size
        if distance > max_sl_pips:
            return "sl_too_far"
    return None


def risk_lot(
    balance: float,
    risk_percent: float,
    entry: float,
    sl: float,
    legs: int,
    value_per_price_unit: float,
    min_lot: float,
    max_lot: float,
    lot_step: float,
) -> Optional[float]:
    """Lot per leg so that all legs together lose `risk_percent` of balance at SL.

    Rounds down to `lot_step` and caps at `max_lot`. Returns None when even
    `min_lot` would exceed the risk budget, so the caller can skip the signal
    rather than over-risk.
    """
    distance = abs(entry - sl)
    if balance <= 0 or distance <= 0 or legs <= 0 or value_per_price_unit <= 0:
        return None
    budget = balance * risk_percent / 100.0
    raw = budget / (distance * value_per_price_unit * legs)
    steps = math.floor(raw / lot_step + 1e-9)
    lot = round(steps * lot_step, 8)
    if lot < min_lot - 1e-9:
        return None
    return round(min(lot, max_lot), 8)


def daily_loss_reached(
    realised_pnl: float,
    balance: Optional[float],
    limit: float,
    limit_percent: float,
) -> bool:
    """True when today's realised loss hits either the money or percent limit."""
    if realised_pnl >= 0:
        return False
    loss = -realised_pnl
    if limit > 0 and loss >= limit:
        return True
    if limit_percent > 0 and balance:
        # Balance already includes today's losses; compare against the start-of-day equivalent.
        start_of_day = balance + loss
        if loss >= start_of_day * limit_percent / 100.0:
            return True
    return False
