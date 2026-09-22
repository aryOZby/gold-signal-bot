"""בדיקת config.yaml לפני הרצה. מצביע על שורת השגיאה המדויקת.

    py scripts\\check_config.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml

CONFIG = ROOT / "config.yaml"


def show_context(lines: list[str], line_no: int, column: int) -> None:
    """מדפיס את האזור סביב השגיאה עם חץ על העמודה."""
    start = max(0, line_no - 4)
    end = min(len(lines), line_no + 3)
    for i in range(start, end):
        marker = ">>" if i == line_no - 1 else "  "
        print(f" {marker} {i + 1:>3} | {lines[i].rstrip()}")
        if i == line_no - 1:
            print(f"      {' ' * 3} | {' ' * max(0, column - 1)}^")


def main() -> int:
    if not CONFIG.exists():
        print(f"!! {CONFIG} לא קיים.")
        return 1

    text = CONFIG.read_text(encoding="utf-8")
    lines = text.splitlines()

    if "\t" in text:
        for i, line in enumerate(lines, start=1):
            if "\t" in line:
                print(f"!! שורה {i} מכילה Tab. ב-YAML מותר רווחים בלבד.")
        return 1

    try:
        yaml.safe_load(text)
    except yaml.YAMLError as exc:
        print("!! שגיאת תחביר ב-config.yaml\n")
        mark = getattr(exc, "problem_mark", None)
        problem = getattr(exc, "problem", str(exc))
        if mark is not None:
            print(f"   {problem}")
            print(f"   שורה {mark.line + 1}, עמודה {mark.column + 1}\n")
            show_context(lines, mark.line + 1, mark.column + 1)
            print(
                "\n   הסיבה הנפוצה: שדה של קבוצה שקיבל הזחה שגויה.\n"
                "   כל השדות של קבוצה חייבים להיות באותה עמודה בדיוק."
            )
        else:
            print(f"   {exc}")
        return 1

    try:
        from src.config import load_config

        cfg = load_config(CONFIG)
    except Exception as exc:
        print(f"!! הקובץ תקין תחבירית אבל נדחה: {exc}")
        return 1

    print("config.yaml תקין.\n")
    print(f"סימול           : {cfg.symbol_override or '(מההודעה)'}")
    print(f"מסחר פעיל       : {cfg.trading_enabled}")
    print(f"dry_run         : {cfg.dry_run}   broker: {cfg.broker_type}")
    print(f"admin_chat_id   : {cfg.admin_chat_id or '(לא מוגדר - אין התראות טלגרם)'}")
    print(f"סיכום יומי      : {cfg.daily_digest_enabled} בשעה "
          f"{cfg.daily_digest_hour:02d}:{cfg.daily_digest_minute:02d}")
    print(f"חודשי במייל     : {cfg.email_monthly} -> "
          f"{', '.join(cfg.email.recipients) or '(לא מוגדר)'}")
    print()
    print(f"{'קבוצה':<22} {'chat_id':>16} {'לוט':>6} {'דילוג':>6} {'קידום':>6}  מצב")
    print("-" * 74)
    for group in cfg.groups:
        skip = group.skip_first_tps if group.skip_first_tps is not None else cfg.skip_first_tps
        be = group.breakeven_after_tp or cfg.breakeven_after_tp
        state = "פעילה" if group.enabled else "מושבתת"
        print(f"{group.name:<22} {group.chat_id:>16} {group.lot:>6} {skip:>6} {be:>6}  {state}")
    print("-" * 74)

    active = [g for g in cfg.groups if g.enabled]
    if not active:
        print("\n!! כל הקבוצות מושבתות. שום איתות לא ייסחר.")
    else:
        print(f"\n{len(active)} קבוצות פעילות. אפשר להריץ:  py main.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
