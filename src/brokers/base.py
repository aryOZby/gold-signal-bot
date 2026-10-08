from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..models import BrokerPosition, ClosedDeal, OrderResult, Side


class Broker(ABC):
    @abstractmethod
    def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def shutdown(self) -> None:
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
    def modify_sl_tp(self, ticket: int, sl: Optional[float], tp: Optional[float]) -> bool:
        raise NotImplementedError

    @abstractmethod
    def positions(self, magic: int) -> list[BrokerPosition]:
        raise NotImplementedError

    @abstractmethod
    def closed_deal(self, ticket: int) -> Optional[ClosedDeal]:
        raise NotImplementedError

    @abstractmethod
    def last_price(self, symbol: str) -> Optional[float]:
        raise NotImplementedError

    def account_balance(self) -> Optional[float]:
        """Account balance, or None when the backend can't report it."""
        return None

    def value_per_price_unit(self, symbol: str) -> Optional[float]:
        """Account-currency P/L of a 1.0 price move for 1 lot, or None if unknown."""
        return None
