"""האזנה לטלגרם בלבד, בלי MT5. מאמת שהקבוצות נקלטות ושהאיתותים מפוענחים.

הרצה:
    py scripts\\listen_only.py            האזנה חיה
    py scripts\\listen_only.py --list     הצגת כל הקבוצות שהחשבון חבר בהן
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telethon import TelegramClient, events
from telethon.utils import get_peer_id

from src.config import group_by_chat_id, group_by_username, load_config
from src.parser import parse_signal
from src.telegram_listener import describe_groups


def _stamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


async def list_dialogs(client: TelegramClient) -> None:
    print("\nקבוצות וערוצים שהחשבון חבר בהם:")
    print(f"{'chat_id':>16}  {'@username':<26} title")
    print("-" * 78)
    async for dialog in client.iter_dialogs():
        if not (dialog.is_group or dialog.is_channel):
            continue
        username = getattr(dialog.entity, "username", None)
        print(f"{dialog.id:>16}  {('@' + username) if username else '':<26} {dialog.name}")
    print("-" * 78)
    print("העתק את ה-chat_id המדויק לתוך config.yaml.\n")


async def run(show_all: bool) -> None:
    cfg = load_config()
    if not cfg.telegram_api_id or not cfg.telegram_api_hash:
        raise SystemExit("חסר TELEGRAM_API_ID / TELEGRAM_API_HASH ב-.env")

    session = Path(cfg.data_dir) / cfg.session_name
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(session), cfg.telegram_api_id, cfg.telegram_api_hash)
    await client.start(phone=cfg.telegram_phone or None)
    me = await client.get_me()
    print(f"מחובר כ-{getattr(me, 'username', None) or me.id} (id={me.id})")

    for group in cfg.groups:
        if not group.username:
            continue
        try:
            entity = await client.get_entity(group.username)
            group.chat_id = int(get_peer_id(entity))
            print(f"נפתר @{group.username} -> chat_id={group.chat_id}")
        except Exception as exc:
            print(f"!! לא הצלחתי לפתור את @{group.username}: {exc}")
            print("   ודא שהחשבון חבר בקבוצה/מנוי בערוץ.")

    if show_all:
        await list_dialogs(client)
        await client.disconnect()
        return

    print(f"\nמאזין ל: {describe_groups(cfg.groups)}")
    print("MT5 לא מעורב כאן. לעצירה: Ctrl+C\n")

    @client.on(events.NewMessage())
    async def handler(event):  # noqa: ANN001
        chat_id = event.chat_id
        if chat_id is None:
            return
        text = event.message.raw_text or ""
        group = group_by_chat_id(cfg, int(chat_id))
        if group is None:
            chat = event.chat or await event.get_chat()
            group = group_by_username(cfg, getattr(chat, "username", None))

        if group is None:
            if text.strip():
                print(f"[{_stamp()}] (מתעלם) chat_id={chat_id}: {text[:60]}")
            return

        print(f"\n[{_stamp()}] הודעה מ-{group.name} (chat_id={chat_id})")
        print("-" * 60)
        print(text[:500])
        print("-" * 60)

        parsed = parse_signal(text)
        if parsed is None:
            print(">> לא זוהה כאיתות (לא תואם את התבנית).\n")
            return
        print(f">> איתות זוהה: {parsed.side.value} {parsed.symbol}")
        print(f"   אזור כניסה : {parsed.zone_low} - {parsed.zone_high}")
        print(f"   SL         : {parsed.sl}")
        print(f"   TP         : {', '.join(str(tp) for tp in parsed.tps)}")
        print(f"   פוזיציות   : {parsed.tp_count} (לוט {group.lot} כל אחת)")
        print("   [מצב האזנה בלבד - לא נשלחה פקודה ל-MT5]\n")

    await client.run_until_disconnected()


def main() -> int:
    parser = argparse.ArgumentParser(description="Telegram listener without MT5")
    parser.add_argument("--list", action="store_true", help="הצג את כל הקבוצות ואת ה-chat_id שלהן")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.list))
    except KeyboardInterrupt:
        print("\nהופסק.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
