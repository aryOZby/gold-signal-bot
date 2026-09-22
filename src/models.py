from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TradeStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    FAILED = "failed"


class SignalStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class CloseReason(str, Enum):
    TP = "TP"
    SL = "SL"
    BREAKEVEN = "BREAKEVEN"
    SAFETY = "SAFETY"
    MANUAL = "MANUAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ParsedSignal:
    symbol: str
    side: Side
    zone_low: float
    zone_high: float
    tps: tuple[float, ...]
    sl: float
    raw_text: str

    @property
    def tp_count(self) -> int:
        return len(self.tps)


@dataclass
class GroupConfig:
    name: str
    chat_id: int
    lot: float
    username: str = ""
    magic: int = 0
    # אסטרטגיה פר-קבוצה. None = לקחת את ברירת המחדל הגלובלית מ-trading.
    skip_first_tps: Optional[int] = None
    breakeven_after_tp: Optional[int] = None
    # false = ממשיכים להאזין ולתעד, אבל לא נכנסים לעסקאות מהקבוצה הזו.
    enabled: bool = True


@dataclass
class OrderResult:
    ok: bool
    ticket: Optional[int]
    fill_price: Optional[float]
    fill_time: Optional[datetime]
    retcode: Optional[int] = None
    message: str = ""
    sl: Optional[float] = None
    tp: Optional[float] = None
    # הנפח שבוצע בפועל. ה-EA יכול לדרוס את גודל הלוט מהגרף, ואז הדוחות
    # צריכים לשקף את מה שנפתח ולא את מה שביקשנו.
    filled_volume: Optional[float] = None


@dataclass
class BrokerPosition:
    ticket: int
    symbol: str
    side: Side
    volume: float
    price_open: float
    sl: float
    tp: float
    profit: float
    comment: str = ""


@dataclass
class ClosedDeal:
    ticket: int
    exit_price: float
    exit_time: datetime
    profit: float
    reason: CloseReason


@dataclass
class TradeRecord:
    id: Optional[int]
    ticket: Optional[int]
    signal_id: str
    group_name: str
    tp_index: int
    tp_price: float
    lot: float
    side: str
    symbol: str
    received_at: datetime
    entry_time: Optional[datetime]
    entry_price: Optional[float]
    sl: Optional[float]
    original_sl: Optional[float]
    sl_moved_to_be: bool
    exit_time: Optional[datetime]
    exit_price: Optional[float]
    close_reason: Optional[str]
    profit: Optional[float]
    pips: Optional[float]
    status: str
    zone_low: float = 0.0
    zone_high: float = 0.0
    telegram_chat_id: int = 0
    telegram_username: str = ""


@dataclass
class SignalRecord:
    id: str
    group_name: str
    chat_id: int
    telegram_msg_id: int
    received_at: datetime
    symbol: str
    side: str
    zone_low: float
    zone_high: float
    sl: float
    raw_text: str
    status: str
    skipped_reason: str = ""
    max_tp_hit: Optional[int] = None
    completed_at: Optional[datetime] = None
    tps: tuple[float, ...] = field(default_factory=tuple)
    username: str = ""
