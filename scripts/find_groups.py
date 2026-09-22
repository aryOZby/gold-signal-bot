"""מציאת chat_id מדויק לפי שם קבוצה, והזרקתו ל-config.yaml.

חיפוש בלבד (מדפיס מועמדים):
    py scripts\\find_groups.py "technical pips" "vip signals room"

כתיבה ל-config.yaml (הפורמט הוא <שם_בקונפיג>=<חיפוש_בטלגרם>):
    py scripts\\find_groups.py --apply "group_a=vip signals room" "plan_group=technical pips"

שמות קבוצות בטלגרם כתובים לעיתים בתווי יוניקוד מעוצבים, למשל
"𝐓𝐞𝐜𝐡𝐧𝐢𝐜𝐚𝐥 𝐏𝐢𝐩𝐬 ™". הנרמול כאן ממיר אותם לאותיות רגילות כדי שחיפוש
טקסט פשוט יתפוס אותם.
"""
from __future__ import annotations

import argparse
import asyncio
import difflib
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from telethon import TelegramClient

from src.config import load_config

CONFIG_PATH = ROOT / "config.yaml"


def normalize(text: str) -> str:
    """'𝐓𝐞𝐜𝐡𝐧𝐢𝐜𝐚𝐥 𝐏𝐢𝐩𝐬 ™' -> 'technical pips tm'"""
    value = unicodedata.normalize("NFKC", text or "")
    value = "".join(c for c in value if not unicodedata.category(c).startswith("So"))
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def score(needle: str, title: str, username: str) -> float:
    target = normalize(title)
    user = normalize(username)
    if not needle:
        return 0.0
    if needle == target or needle == user:
        return 1.0
    if needle in target or needle in user:
        return 0.9
    return difflib.SequenceMatcher(None, needle, target).ratio()


async def collect_dialogs(client: TelegramClient) -> list[dict]:
    rows = []
    async for dialog in client.iter_dialogs():
        if not (dialog.is_group or dialog.is_channel):
            continue
        rows.append(
            {
                "id": int(dialog.id),
                "title": dialog.name or "",
                "username": getattr(dialog.entity, "username", None) or "",
            }
        )
    return rows


def best_matches(rows: list[dict], needle: str, limit: int = 5) -> list[tuple[float, dict]]:
    key = normalize(needle)
    scored = [(score(key, r["title"], r["username"]), r) for r in rows]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [pair for pair in scored[:limit] if pair[0] > 0.3]


def patch_config(path: Path, updates: dict[str, int]) -> list[str]:
    """מעדכן chat_id בערכי groups קיימים, בלי לפגוע בהערות או בשאר הקובץ."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    changed: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        match = re.match(r"^(\s*)-\s+name:\s*(.+?)\s*$", line)
        if not match:
            i += 1
            continue
        name = match.group(2).strip().strip("\"'")
        if name not in updates:
            i += 1
            continue

        item_indent = match.group(1) + "  "
        body: list[str] = []
        replaced = False
        j = i + 1
        while j < len(lines):
            nxt = lines[j]
            if nxt.strip() and not nxt.startswith(item_indent):
                break
            if re.match(r"^\s*chat_id\s*:", nxt):
                body.append(f"{item_indent}chat_id: {updates[name]}\n")
                replaced = True
            else:
                body.append(nxt)
            j += 1
        if not replaced:
            body.insert(0, f"{item_indent}chat_id: {updates[name]}\n")
        out.extend(body)
        changed.append(name)
        i = j

    if changed:
        backup = path.with_suffix(path.suffix + ".bak")
        backup.write_text("".join(lines), encoding="utf-8")
        path.write_text("".join(out), encoding="utf-8")
    return changed


def show_matches(rows: list[dict], needle: str) -> None:
    matches = best_matches(rows, needle)
    if not matches:
        print("   לא נמצאה התאמה. נסה מילה אחת בלבד מתוך השם.\n")
        return
    for rank, (points, row) in enumerate(matches, start=1):
        mark = "*" if rank == 1 else " "
        user = f"@{row['username']}" if row["username"] else ""
        print(f" {mark} {row['id']:>16}  {points:.2f}  {user:<26} {row['title']}")
    print()


def interactive(rows: list[dict], cfg) -> None:
    print("קבוצות שכבר מוגדרות ב-config.yaml:")
    for group in cfg.groups:
        target = group.chat_id or (f"@{group.username}" if group.username else "?")
        print(f"   {group.name:<24} {target}")
    print()
    print("הקלד שם קבוצה לחיפוש. אפשר באנגלית פשוטה גם אם בטלגרם השם מעוצב.")
    print("Enter ריק מסיים.\n")
    while True:
        try:
            needle = input("חפש> ").strip()
        except EOFError:
            break
        if not needle:
            break
        show_matches(rows, needle)
    print("סיום. להזרקה אוטומטית ל-config.yaml הרץ:")
    print('   py scripts\\find_groups.py --apply "<שם_בקונפיג>=<חיפוש>"')


async def run(terms: list[str], apply: bool) -> int:
    cfg = load_config()
    if not cfg.telegram_api_id or not cfg.telegram_api_hash:
        raise SystemExit("חסר TELEGRAM_API_ID / TELEGRAM_API_HASH ב-.env")

    session = Path(cfg.data_dir) / cfg.session_name
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(session), cfg.telegram_api_id, cfg.telegram_api_hash)
    await client.start(phone=cfg.telegram_phone or None)
    rows = await collect_dialogs(client)
    await client.disconnect()
    print(f"נסרקו {len(rows)} קבוצות וערוצים.\n")

    if not terms:
        interactive(rows, cfg)
        return 0

    resolved: dict[str, int] = {}
    for term in terms:
        if apply:
            if "=" not in term:
                print(f"!! '{term}' חייב להיות בפורמט <שם_בקונפיג>=<חיפוש>")
                continue
            config_name, needle = term.split("=", 1)
            config_name = config_name.strip()
        else:
            config_name, needle = "", term

        matches = best_matches(rows, needle)
        label = f"{config_name} <- '{needle}'" if config_name else f"'{needle}'"
        print(f"=== {label} ===")
        show_matches(rows, needle)
        if config_name and matches:
            resolved[config_name] = matches[0][1]["id"]

    if not apply:
        return 0
    if not resolved:
        print("אין מה לעדכן.")
        return 1

    known = {g.name for g in cfg.groups}
    missing = [name for name in resolved if name not in known]
    if missing:
        print(f"!! השמות הבאים לא קיימים ב-config.yaml: {', '.join(missing)}")
        print("   הוסף אותם ידנית תחת telegram.groups ואז הרץ שוב.")
        for name in missing:
            resolved.pop(name)
    if not resolved:
        return 1

    changed = patch_config(CONFIG_PATH, resolved)
    for name in changed:
        print(f"עודכן {name}: chat_id = {resolved[name]}")
    print(f"\nגיבוי נשמר ב-{CONFIG_PATH.name}.bak")
    print("לאימות:  py scripts\\listen_only.py")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve exact Telegram chat ids by name")
    parser.add_argument(
        "terms",
        nargs="*",
        help="שם לחיפוש, או <שם_בקונפיג>=<חיפוש> עם --apply. בלי ארגומנטים נכנסים למצב אינטראקטיבי",
    )
    parser.add_argument("--apply", action="store_true", help="כתוב את התוצאות ל-config.yaml")
    args = parser.parse_args()
    try:
        return asyncio.run(run(args.terms, args.apply))
    except KeyboardInterrupt:
        return 1


if __name__ == "__main__":
    sys.exit(main())
