from __future__ import annotations

import itertools
import threading
from datetime import datetime, timezone
from typing import Optional

from ..models import BrokerPosition, ClosedDeal, CloseReason, OrderResult, Side
from ..timeutil import utcnow
from .base import Broker


class DryRunBroker(Broker):
    """In-memory broker for tests and first-run validation. No real orders."""

    def __init__(self, fill_offset: float = 0.0):
        self._lock = threading.Lock()
        self._positions: dict[int, BrokerPosition] = {}
        self._closed: dict[int, ClosedDeal] = {}
        self._tickets = itertools.count(1_000_001)
        self._fill_offset = fill_offset
        self._last_price: dict[str, float] = {}

    def connect(self) -> None:
        return

    def shutdown(self) -> None:
        return

    def market_order(
        self,
        symbol: str,
        side: Side,
        volume: float,
        sl: float,
        tp: float,
        comment: str,
        deviation: int,
        magic: int,
    ) -> OrderResult:
        now = utcnow()
        fill = self._last_price.get(symbol)
        if fill is None:
            fill = (sl + tp) / 2.0 + self._fill_offset
        ticket = next(self._tickets)
        pos = BrokerPosition(
            ticket=ticket,
            symbol=symbol,
            side=side,
            volume=volume,
            price_open=fill,
            sl=sl,
            tp=tp,
            profit=0.0,
            comment=comment,
        )
        with self._lock:
            self._positions[ticket] = pos
            self._last_price[symbol] = fill
        return OrderResult(
            ok=True,
            ticket=ticket,
            fill_price=fill,
            fill_time=now,
            retcode=0,
            message="dry_run",
            sl=sl,
            tp=tp,
        )

    def modify_sl_tp(self, ticket: int, sl: Optional[float], tp: Optional[float]) -> bool:
        with self._lock:
            pos = self._positions.get(ticket)
            if not pos:
                return False
            self._positions[ticket] = BrokerPosition(
                ticket=pos.ticket,
                symbol=pos.symbol,
                side=pos.side,
                volume=pos.volume,
                price_open=pos.price_open,
                sl=pos.sl if sl is None else sl,
                tp=pos.tp if tp is None else tp,
                profit=pos.profit,
                comment=pos.comment,
            )
        return True

    def positions(self, magic: int) -> list[BrokerPosition]:
        with self._lock:
            return list(self._positions.values())

    def closed_deal(self, ticket: int) -> Optional[ClosedDeal]:
        with self._lock:
            return self._closed.get(ticket)

    def last_price(self, symbol: str) -> Optional[float]:
        return self._last_price.get(symbol)

    def simulate_close(
        self,
        ticket: int,
        reason: CloseReason,
        exit_price: Optional[float] = None,
        profit: float = 0.0,
    ) -> None:
        with self._lock:
            pos = self._positions.pop(ticket, None)
            if not pos:
                return
            price = exit_price if exit_price is not None else pos.tp
            self._closed[ticket] = ClosedDeal(
                ticket=ticket,
                exit_price=price,
                exit_time=datetime.now(timezone.utc),
                profit=profit,
                reason=reason,
            )

    def set_price(self, symbol: str, price: float) -> None:
        self._last_price[symbol] = price
