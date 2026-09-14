#!/usr/bin/env python3
"""First-time Telegram login — creates data/<session>.session"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config  # noqa: E402
from src.logging_setup import setup_logging  # noqa: E402


async def _run(force_sms: bool) -> int:
    cfg = load_config()
    setup_logging(cfg.logs_dir)
    if not cfg.telegram_api_id or not cfg.telegram_api_hash:
        print("חסר TELEGRAM_API_ID / TELEGRAM_API_HASH בקובץ .env")
        return 1
    phone = (cfg.telegram_phone or "").strip()
    if not phone:
        print("חסר TELEGRAM_PHONE ב-.env (למשל +972501234567)")
        return 1
    if not phone.startswith("+"):
        print("TELEGRAM_PHONE חייב להתחיל ב-+ וקידומת מדינה")
        return 1

    from telethon import TelegramClient
    from telethon.errors import (
        PhoneCodeExpiredError,
        PhoneCodeInvalidError,
        SessionPasswordNeededError,
    )

    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    session = cfg.data_dir / cfg.session_name
    client = TelegramClient(str(session), cfg.telegram_api_id, cfg.telegram_api_hash)
    await client.connect()
    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"כבר מחובר כ-{getattr(me, 'username', None) or me.id}")
        await client.disconnect()
        return 0

    print(f"שולח קוד ל-{phone}" + (" ב-SMS" if force_sms else " לאפליקציית טלגרם"))
    print("אם זה באפליקציה: לפעמים זה מסך קופץ, לא הודעה בצ'אט.")
    sent = await client.send_code_request(phone, force_sms=force_sms)
    print(f"שיטת שליחה: {type(sent.type).__name__}")
    code = input("הקלד את הקוד (ספרות בלבד): ").strip()
    try:
        await client.sign_in(phone, code)
    except PhoneCodeInvalidError:
        print("קוד שגוי. הרץ שוב וקח את הקוד החדש.")
        await client.disconnect()
        return 1
    except PhoneCodeExpiredError:
        print("הקוד פג. הרץ שוב.")
        await client.disconnect()
        return 1
    except SessionPasswordNeededError:
        password = getpass.getpass("סיסמת Two-Step Verification של טלגרם: ")
        await client.sign_in(password=password)

    me = await client.get_me()
    print(f"מחובר כ-{getattr(me, 'username', None) or me.id} (id={me.id})")
    await client.disconnect()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sms", action="store_true", help="בקש קוד ב-SMS במקום באפליקציה")
    args = parser.parse_args()
    return asyncio.run(_run(force_sms=args.sms))


if __name__ == "__main__":
    raise SystemExit(main())
