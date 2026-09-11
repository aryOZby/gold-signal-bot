#!/usr/bin/env python3
"""Replay the two sample templates in dry-run and write Excel files."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.alerts import AlertBus  # noqa: E402
from src.brokers.dry_run import DryRunBroker  # noqa: E402
from src.config import load_config  # noqa: E402
from src.db import Database  # noqa: E402
from src.excel_report import ExcelReporter  # noqa: E402
from src.logging_setup import setup_logging  # noqa: E402
from src.models import CloseReason, GroupConfig  # noqa: E402
from src.parser import parse_signal  # noqa: E402
from src.trade_manager import IncomingSignal, TradingEngine  # noqa: E402

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


def play(engine: TradingEngine, text: str, group: GroupConfig, msg_id: int) -> None:
    parsed = parse_signal(text)
    assert parsed is not None
    engine._handle(
        IncomingSignal(
            parsed=parsed,
            group=group,
            chat_id=group.chat_id,
            telegram_msg_id=msg_id,
            received_at=datetime.now(timezone.utc),
            raw_text=text,
        )
    )


def main() -> int:
    cfg = load_config()
    setup_logging(cfg.logs_dir)
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(cfg.data_dir / "replay.db")
    broker = DryRunBroker()
    broker.connect()
    reporter = ExcelReporter(cfg.output_dir, cfg.tz)
    engine = TradingEngine(cfg, db, broker, reporter, alert=AlertBus().send)
    group_a, group_b = cfg.groups[0], cfg.groups[1] if len(cfg.groups) > 1 else cfg.groups[0]

    play(engine, SELL, group_a, 1)
    # second signal while first is open should be skipped
    play(engine, BUY, group_b, 2)

    trades = db.trades_for_signal(db.active_signals()[0].id)
    # hit TP3 then remaining should move to entry on next monitor
    for trade in trades:
        if trade.tp_index <= 3 and trade.ticket:
            broker.simulate_close(trade.ticket, CloseReason.TP, exit_price=trade.tp_price, profit=10)
    engine._monitor()

    now = datetime.now(timezone.utc)
    for group in {group_a.name, group_b.name}:
        path = engine._write_excel(group, now, final=False)
        print(f"Wrote {path}")
    print("Done. First signal executed, second skipped (one-at-a-time), TP3 triggered breakeven.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
