from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import SignalRecord, TradeRecord
from .timeutil import iso, parse_iso


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init()

    def _init(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    id TEXT PRIMARY KEY,
                    group_name TEXT NOT NULL,
                    chat_id INTEGER NOT NULL,
                    telegram_msg_id INTEGER NOT NULL,
                    received_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    zone_low REAL NOT NULL,
                    zone_high REAL NOT NULL,
                    sl REAL NOT NULL,
                    raw_text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    skipped_reason TEXT NOT NULL DEFAULT '',
                    max_tp_hit INTEGER,
                    completed_at TEXT,
                    UNIQUE(chat_id, telegram_msg_id)
                );

                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket INTEGER UNIQUE,
                    signal_id TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    tp_index INTEGER NOT NULL,
                    tp_price REAL NOT NULL,
                    lot REAL NOT NULL,
                    side TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    entry_time TEXT,
                    entry_price REAL,
                    sl REAL,
                    original_sl REAL,
                    sl_moved_to_be INTEGER NOT NULL DEFAULT 0,
                    exit_time TEXT,
                    exit_price REAL,
                    close_reason TEXT,
                    profit REAL,
                    pips REAL,
                    status TEXT NOT NULL,
                    zone_low REAL NOT NULL DEFAULT 0,
                    zone_high REAL NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_trades_signal ON trades(signal_id);
                CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
                CREATE INDEX IF NOT EXISTS idx_signals_group_time ON signals(group_name, received_at);
                CREATE INDEX IF NOT EXISTS idx_trades_group_time ON trades(group_name, received_at);
                """
            )
            self._ensure_column("trades", "telegram_chat_id", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column("trades", "telegram_username", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("signals", "username", "TEXT NOT NULL DEFAULT ''")
            self._conn.commit()

    def _ensure_column(self, table: str, name: str, decl: str) -> None:
        rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {str(r[1]) for r in rows}
        if name not in existing:
            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")

    def already_processed(self, chat_id: int, telegram_msg_id: int) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM signals WHERE chat_id=? AND telegram_msg_id=?",
                (chat_id, telegram_msg_id),
            ).fetchone()
        return row is not None

    def insert_signal(self, rec: SignalRecord) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO signals (
                    id, group_name, chat_id, telegram_msg_id, received_at, symbol, side,
                    zone_low, zone_high, sl, raw_text, status, skipped_reason, max_tp_hit,
                    completed_at, username
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec.id,
                    rec.group_name,
                    rec.chat_id,
                    rec.telegram_msg_id,
                    iso(rec.received_at),
                    rec.symbol,
                    rec.side,
                    rec.zone_low,
                    rec.zone_high,
                    rec.sl,
                    rec.raw_text,
                    rec.status,
                    rec.skipped_reason,
                    rec.max_tp_hit,
                    iso(rec.completed_at),
                    rec.username,
                ),
            )
            self._conn.commit()

    def insert_trade(self, rec: TradeRecord) -> int:
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO trades (
                    ticket, signal_id, group_name, tp_index, tp_price, lot, side, symbol,
                    received_at, entry_time, entry_price, sl, original_sl, sl_moved_to_be,
                    exit_time, exit_price, close_reason, profit, pips, status, zone_low, zone_high,
                    telegram_chat_id, telegram_username
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec.ticket,
                    rec.signal_id,
                    rec.group_name,
                    rec.tp_index,
                    rec.tp_price,
                    rec.lot,
                    rec.side,
                    rec.symbol,
                    iso(rec.received_at),
                    iso(rec.entry_time),
                    rec.entry_price,
                    rec.sl,
                    rec.original_sl,
                    int(rec.sl_moved_to_be),
                    iso(rec.exit_time),
                    rec.exit_price,
                    rec.close_reason,
                    rec.profit,
                    rec.pips,
                    rec.status,
                    rec.zone_low,
                    rec.zone_high,
                    rec.telegram_chat_id,
                    rec.telegram_username,
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def update_trade(self, rec: TradeRecord) -> None:
        if rec.id is None:
            raise ValueError("trade id required")
        with self._lock:
            self._conn.execute(
                """
                UPDATE trades SET
                    ticket=?, entry_time=?, entry_price=?, sl=?, original_sl=?,
                    sl_moved_to_be=?, exit_time=?, exit_price=?, close_reason=?,
                    profit=?, pips=?, status=?
                WHERE id=?
                """,
                (
                    rec.ticket,
                    iso(rec.entry_time),
                    rec.entry_price,
                    rec.sl,
                    rec.original_sl,
                    int(rec.sl_moved_to_be),
                    iso(rec.exit_time),
                    rec.exit_price,
                    rec.close_reason,
                    rec.profit,
                    rec.pips,
                    rec.status,
                    rec.id,
                ),
            )
            self._conn.commit()

    def update_signal_status(
        self,
        signal_id: str,
        status: str,
        skipped_reason: str = "",
        max_tp_hit: Optional[int] = None,
        completed_at: Optional[datetime] = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE signals
                SET status=?, skipped_reason=?, max_tp_hit=?, completed_at=?
                WHERE id=?
                """,
                (status, skipped_reason, max_tp_hit, iso(completed_at), signal_id),
            )
            self._conn.commit()

    def mark_breakeven(self, trade_id: int, new_sl: float) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE trades SET sl=?, sl_moved_to_be=1 WHERE id=?",
                (new_sl, trade_id),
            )
            self._conn.commit()

    def open_trades(self) -> list[TradeRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM trades WHERE status='open' ORDER BY id"
            ).fetchall()
        return [self._trade_from_row(r) for r in rows]

    def trades_for_signal(self, signal_id: str) -> list[TradeRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM trades WHERE signal_id=? ORDER BY tp_index",
                (signal_id,),
            ).fetchall()
        return [self._trade_from_row(r) for r in rows]

    def get_signal(self, signal_id: str) -> Optional[SignalRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM signals WHERE id=?", (signal_id,)
            ).fetchone()
        return self._signal_from_row(row) if row else None

    def active_signals(self) -> list[SignalRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM signals WHERE status='active' ORDER BY received_at"
            ).fetchall()
        return [self._signal_from_row(r) for r in rows]

    def trades_in_range(
        self, group_name: str, start: datetime, end: datetime
    ) -> list[TradeRecord]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM trades
                WHERE group_name=? AND received_at >= ? AND received_at < ?
                ORDER BY received_at, tp_index
                """,
                (group_name, iso(start), iso(end)),
            ).fetchall()
        return [self._trade_from_row(r) for r in rows]

    def signals_in_range(
        self, group_name: str, start: datetime, end: datetime
    ) -> list[SignalRecord]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM signals
                WHERE group_name=? AND received_at >= ? AND received_at < ?
                ORDER BY received_at
                """,
                (group_name, iso(start), iso(end)),
            ).fetchall()
        return [self._signal_from_row(r) for r in rows]

    def get_meta(self, key: str) -> Optional[str]:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key=?", (key,)
            ).fetchone()
        return str(row["value"]) if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            self._conn.commit()

    @staticmethod
    def _trade_from_row(row: sqlite3.Row) -> TradeRecord:
        return TradeRecord(
            id=row["id"],
            ticket=row["ticket"],
            signal_id=row["signal_id"],
            group_name=row["group_name"],
            tp_index=row["tp_index"],
            tp_price=row["tp_price"],
            lot=row["lot"],
            side=row["side"],
            symbol=row["symbol"],
            received_at=parse_iso(row["received_at"]),
            entry_time=parse_iso(row["entry_time"]),
            entry_price=row["entry_price"],
            sl=row["sl"],
            original_sl=row["original_sl"],
            sl_moved_to_be=bool(row["sl_moved_to_be"]),
            exit_time=parse_iso(row["exit_time"]),
            exit_price=row["exit_price"],
            close_reason=row["close_reason"],
            profit=row["profit"],
            pips=row["pips"],
            status=row["status"],
            zone_low=row["zone_low"] or 0.0,
            zone_high=row["zone_high"] or 0.0,
            telegram_chat_id=int(_row_get(row, "telegram_chat_id", 0) or 0),
            telegram_username=str(_row_get(row, "telegram_username", "") or ""),
        )

    @staticmethod
    def _signal_from_row(row: sqlite3.Row) -> SignalRecord:
        return SignalRecord(
            id=row["id"],
            group_name=row["group_name"],
            chat_id=row["chat_id"],
            telegram_msg_id=row["telegram_msg_id"],
            received_at=parse_iso(row["received_at"]),
            symbol=row["symbol"],
            side=row["side"],
            zone_low=row["zone_low"],
            zone_high=row["zone_high"],
            sl=row["sl"],
            raw_text=row["raw_text"],
            status=row["status"],
            skipped_reason=row["skipped_reason"] or "",
            max_tp_hit=row["max_tp_hit"],
            completed_at=parse_iso(row["completed_at"]),
            username=str(_row_get(row, "username", "") or ""),
        )


def _row_get(row: sqlite3.Row, key: str, default=None):
    try:
        return row[key]
    except (IndexError, KeyError):
        return default
