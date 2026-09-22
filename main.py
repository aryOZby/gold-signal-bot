from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

from src.alerts import AlertBus
from src.brokers.factory import make_broker
from src.config import load_config
from src.db import Database
from src.excel_report import ExcelReporter
from src.logging_setup import setup_logging
from src.telegram_listener import TelegramService, describe_groups
from src.trade_manager import TradingEngine

_LOG = logging.getLogger(__name__)


def build_engine(cfg):
    db = Database(cfg.data_dir / "bot.db")
    broker = make_broker(cfg)
    reporter = ExcelReporter(cfg.output_dir, cfg.tz)
    alerts = AlertBus()
    engine = TradingEngine(cfg, db, broker, reporter, alert=alerts.send)
    return engine, alerts


def main() -> int:
    parser = argparse.ArgumentParser(description="Telegram → MT5 gold signal bot")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    try:
        cfg = load_config(Path(args.config) if args.config else None)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" (שורה {mark.line + 1}, עמודה {mark.column + 1})" if mark else ""
        print(f"שגיאת תחביר ב-config.yaml{where}: {getattr(exc, 'problem', exc)}")
        print("להצגת השורה המדויקת הרץ:  py scripts\\check_config.py")
        return 1
    except (ValueError, KeyError) as exc:
        print(f"config.yaml נדחה: {exc}")
        print("לבדיקה מלאה הרץ:  py scripts\\check_config.py")
        return 1
    setup_logging(cfg.logs_dir)
    _LOG.info(
        "Starting dry_run=%s broker=%s groups=%s",
        cfg.dry_run,
        cfg.broker_type,
        describe_groups(cfg.groups),
    )
    placeholders = {-1000000000001, -1000000000002}
    missing = [g for g in cfg.groups if g.chat_id in placeholders or (not g.chat_id and not g.username)]
    if missing:
        _LOG.warning(
            "עדיין חסר מזהה לקבוצות: %s. עדכן config.yaml או הרץ python scripts/list_chats.py",
            ", ".join(g.name for g in missing),
        )
    if not cfg.telegram_api_id or not cfg.telegram_api_hash:
        _LOG.error("Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env (from https://my.telegram.org)")
        return 1

    engine, alerts = build_engine(cfg)
    engine.start()
    service = TelegramService(cfg, engine, alerts)

    try:
        import asyncio

        async def runner():
            await service.start()
            await service.run_until_disconnected()

        asyncio.run(runner())
    except KeyboardInterrupt:
        _LOG.info("Interrupted")
    finally:
        engine.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
