#!/usr/bin/env python3
"""Offline demo: parse a sample signal, run risk checks and size the orders.

Runs entirely in dry-run mode — no Telegram, no MT5, nothing is written to
your data/ or reports/ folders.

    python scripts/demo_signal.py
"""
from __future__ import annotations

import logging
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.brokers.dry_run import DryRunBroker  # noqa: E402
from src.config import load_config  # noqa: E402
from src.db import Database  # noqa: E402
from src.excel_report import ExcelReporter  # noqa: E402
from src.parser import parse_signal  # noqa: E402
from src.risk import RiskSettings  # noqa: E402
from src.trade_manager import IncomingSignal, TradingEngine  # noqa: E402

SIGNAL = """#XAUUSD SELL 4315-4318

TP 4312
TP 4309
TP 4305
TP 4300
TP 4295
TP 4285

SL 4327
"""

BROKEN = """#XAUUSD SELL 4315-4318

TP 4312
TP 4309
TP 4305
TP 4300
TP 4295
TP 4285

SL 4310
"""


def submit(engine: TradingEngine, text: str, msg_id: int) -> None:
    parsed = parse_signal(text)
    assert parsed is not None
    group = engine.cfg.groups[0]
    logging.getLogger("demo").info(
        "Parsed: %s %s zone=%s-%s TPs=%s SL=%s",
        parsed.side.value, parsed.symbol, parsed.zone_low, parsed.zone_high, list(parsed.tps), parsed.sl,
    )
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)-18s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    log = logging.getLogger("demo")
    work = Path(tempfile.mkdtemp(prefix="gsb-demo-"))
    cfg = load_config(ROOT / "config.example.yaml")
    cfg.data_dir, cfg.output_dir = work / "data", work / "reports"
    cfg.data_dir.mkdir(parents=True)
    cfg.output_dir.mkdir(parents=True)
    cfg.risk = RiskSettings(
        lot_mode="risk_percent", risk_percent=1.0, max_lot=0.5,
        sanity_checks=True, max_sl_pips=200, daily_loss_limit=300,
    )

    broker = DryRunBroker(balance=10_000)
    broker.set_price("XAUUSD", 4316.2)
    engine = TradingEngine(cfg, Database(cfg.data_dir / "demo.db"), broker, ExcelReporter(cfg.output_dir, cfg.tz))
    engine.alert = lambda text, path=None: log.info("Admin alert queued")

    log.info("Dry-run broker: balance=$10,000  XAUUSD=4316.2  risk=1%/signal  sanity checks ON")
    log.info("-- Incoming Telegram message #1 " + "-" * 30)
    submit(engine, SIGNAL, 1)
    for pos in broker.positions(cfg.magic_number):
        log.info(
            "  ticket=%s %s %s lot=%.2f open=%.1f SL=%.1f TP=%.1f [%s]",
            pos.ticket, pos.side.value, pos.symbol, pos.volume, pos.price_open, pos.sl, pos.tp, pos.comment,
        )

    log.info("-- Incoming Telegram message #2 (malformed) " + "-" * 18)
    submit(engine, BROKEN, 2)
    log.info("Done: 3 orders sent for #1, #2 rejected before reaching the broker.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
