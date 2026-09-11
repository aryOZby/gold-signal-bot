from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from src.brokers.dry_run import DryRunBroker
from src.config import AppConfig
from src.db import Database
from src.excel_report import ExcelReporter
from src.models import CloseReason, GroupConfig
from src.parser import parse_signal
from src.trade_manager import IncomingSignal, TradingEngine

SELL = """#XAUUSD SELL 4315-4318

TP 4312
TP 4309
TP 4305
TP 4300
TP 4295
TP 4285

SL 4327
"""

BUY = """#XAUUSD BUY 4349-4346

TP 4352
TP 4355
TP 4359
TP 4364
TP 4369
TP 4379

SL 4337
"""


def _cfg(tmp: Path) -> AppConfig:
    tz = ZoneInfo("Asia/Jerusalem")
    return AppConfig(
        timezone="Asia/Jerusalem",
        dry_run=True,
        session_name="test",
        groups=[
            GroupConfig("group_a", -1001, 0.01),
            GroupConfig("group_b", -1002, 0.01),
        ],
        admin_chat_id=0,
        telegram_api_id=0,
        telegram_api_hash="",
        telegram_phone="",
        symbol_override="",
        max_concurrent_signals=1,
        breakeven_after_tp=3,
        safety_delay_seconds=5,
        safety_pips=50,
        pip_size=0.1,
        magic_number=260908,
        deviation=30,
        order_retries=0,
        broker_type="dry_run",
        common_files_dir="",
        mt5_login=None,
        mt5_password="",
        mt5_server="",
        mt5_terminal_path="",
        output_dir=tmp / "reports",
        daily_digest_hour=23,
        daily_digest_minute=55,
        data_dir=tmp / "data",
        logs_dir=tmp / "logs",
        lot_size_default=0.01,
        tz=tz,
    )


def _engine(tmp: Path) -> tuple[TradingEngine, Database, DryRunBroker]:
    cfg = _cfg(tmp)
    cfg.data_dir.mkdir(parents=True)
    cfg.output_dir.mkdir(parents=True)
    db = Database(cfg.data_dir / "bot.db")
    broker = DryRunBroker()
    broker.connect()
    reporter = ExcelReporter(cfg.output_dir, cfg.tz)
    engine = TradingEngine(cfg, db, broker, reporter)
    return engine, db, broker


def _incoming(text: str, group: GroupConfig, msg_id: int) -> IncomingSignal:
    parsed = parse_signal(text)
    assert parsed is not None
    return IncomingSignal(
        parsed=parsed,
        group=group,
        chat_id=group.chat_id,
        telegram_msg_id=msg_id,
        received_at=datetime.now(timezone.utc),
        raw_text=text,
    )


def test_execute_then_persist(tmp_path: Path):
    engine, db, broker = _engine(tmp_path)
    group = engine.cfg.groups[0]
    engine._handle(_incoming(SELL, group, 11))
    signals = db.active_signals()
    assert len(signals) == 1
    trades = db.trades_for_signal(signals[0].id)
    assert len(trades) == 6
    assert all(t.status == "open" and t.ticket for t in trades)
    assert [t.tp_index for t in trades] == [1, 2, 3, 4, 5, 6]
    assert broker.positions(engine.cfg.magic_number)
    path = engine._write_excel(group.name, datetime.now(timezone.utc), final=False)
    assert path and Path(path).exists()


def test_one_signal_at_a_time(tmp_path: Path):
    engine, db, _broker = _engine(tmp_path)
    a, b = engine.cfg.groups
    engine._handle(_incoming(SELL, a, 1))
    engine._handle(_incoming(BUY, b, 2))
    skipped = [s for s in db.signals_in_range(b.name, datetime(2020, 1, 1, tzinfo=timezone.utc), datetime(2030, 1, 1, tzinfo=timezone.utc)) if s.status == "skipped"]
    assert len(skipped) == 1
    assert skipped[0].skipped_reason == "busy_one_signal"
    assert len(db.active_signals()) == 1


def test_tp3_moves_remaining_stops_to_entry(tmp_path: Path):
    engine, db, broker = _engine(tmp_path)
    group = engine.cfg.groups[0]
    engine._handle(_incoming(SELL, group, 3))
    sid = db.active_signals()[0].id
    trades = db.trades_for_signal(sid)
    for trade in trades:
        if trade.tp_index <= 3 and trade.ticket:
            broker.simulate_close(trade.ticket, CloseReason.TP, exit_price=trade.tp_price, profit=8)
    engine._monitor()
    remaining = [t for t in db.trades_for_signal(sid) if t.status == "open"]
    assert len(remaining) == 3
    assert all(t.sl_moved_to_be for t in remaining)
    assert all(t.sl == t.entry_price for t in remaining)


def test_safety_fills_missing_sl_tp(tmp_path: Path):
    engine, db, broker = _engine(tmp_path)
    group = engine.cfg.groups[0]
    engine._handle(_incoming(SELL, group, 4))
    trade = db.open_trades()[0]
    assert trade.ticket is not None
    broker.modify_sl_tp(trade.ticket, sl=0.0, tp=0.0)
    engine._apply_safety(trade.signal_id)
    pos = {p.ticket: p for p in broker.positions(engine.cfg.magic_number)}[trade.ticket]
    assert pos.sl != 0
    assert pos.tp != 0
    delta = engine.cfg.safety_pips * engine.cfg.pip_size
    assert abs(pos.sl - (trade.entry_price + delta)) < 1e-6
    assert abs(pos.tp - (trade.entry_price - delta)) < 1e-6
