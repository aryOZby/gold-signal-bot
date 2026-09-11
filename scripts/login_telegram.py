#!/usr/bin/env python3
"""First-time Telegram login — creates data/<session>.session"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config  # noqa: E402
from src.logging_setup import setup_logging  # noqa: E402


async def _run() -> int:
    cfg = load_config()
    setup_logging(cfg.logs_dir)
    if not cfg.telegram_api_id or not cfg.telegram_api_hash:
        print("חסר TELEGRAM_API_ID / TELEGRAM_API_HASH בקובץ .env")
        print("ניגשים ל-https://my.telegram.org → API development tools")
        return 1
    from telethon import TelegramClient

    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    session = cfg.data_dir / cfg.session_name
    client = TelegramClient(str(session), cfg.telegram_api_id, cfg.telegram_api_hash)
    await client.start(phone=cfg.telegram_phone or None)
    me = await client.get_me()
    print(f"מחובר כ-{getattr(me, 'username', None) or me.id}")
    print("הרץ עכשיו: python scripts/list_chats.py כדי לראות את ה-ID של הקבוצות")
    await client.disconnect()
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
