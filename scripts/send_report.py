"""שליחת דוח חודשי במייל ידנית, בלי לחכות ל-01 לחודש.

    py scripts\\send_report.py                 החודש הנוכחי
    py scripts\\send_report.py --prev          החודש הקודם
    py scripts\\send_report.py --year 2026 --month 9
    py scripts\\send_report.py --check         בדיקת הגדרות SMTP בלבד
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config
from src.db import Database
from src.excel_report import ExcelReporter
from src.emailer import EmailSender


def main() -> int:
    parser = argparse.ArgumentParser(description="Send the monthly report by email")
    parser.add_argument("--year", type=int)
    parser.add_argument("--month", type=int)
    parser.add_argument("--prev", action="store_true", help="החודש הקודם")
    parser.add_argument("--check", action="store_true", help="הצג הגדרות SMTP ובדוק חיבור")
    args = parser.parse_args()

    cfg = load_config()
    mailer = EmailSender(cfg.email)

    print("הגדרות מייל:")
    print(f"  SMTP_HOST  = {cfg.email.host or '(ריק)'}")
    print(f"  SMTP_PORT  = {cfg.email.port}")
    print(f"  SMTP_USER  = {cfg.email.user or '(ריק)'}")
    print(f"  SMTP_PASSWORD = {'*' * len(cfg.email.password) if cfg.email.password else '(ריק)'}")
    print(f"  EMAIL_TO   = {', '.join(cfg.email.recipients) or '(ריק)'}")
    print()

    if not mailer.enabled:
        print("!! המייל לא מוגדר. צריך לפחות SMTP_HOST ו-EMAIL_TO ב-.env")
        return 1

    if args.check:
        ok = mailer.send(
            "בדיקה — gold-signal-bot",
            "אם קיבלת את ההודעה הזו, שליחת הדוחות החודשיים במייל מוגדרת נכון.",
        )
        print("נשלח בהצלחה." if ok else "השליחה נכשלה. ראה את הלוג למעלה.")
        return 0 if ok else 1

    now = datetime.now(cfg.tz)
    year, month = now.year, now.month
    if args.prev:
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    if args.year:
        year = args.year
    if args.month:
        month = args.month

    db = Database(cfg.data_dir / "bot.db")
    reporter = ExcelReporter(cfg.output_dir, cfg.tz)

    from src.excel_report import month_bounds

    start, end = month_bounds(year, month, cfg.tz)
    paths: list[Path] = []
    for group in cfg.groups:
        signals = db.signals_in_range(group.name, start, end)
        trades = db.trades_in_range(group.name, start, end)
        path = reporter.write_month(group.name, year, month, signals, trades, final=False)
        paths.append(path)
        print(f"{group.name}: {len(signals)} איתותים, {len(trades)} עסקאות -> {path}")

    lines = [f"דוח {year:04d}-{month:02d}", ""]
    for group in cfg.groups:
        trades = db.trades_in_range(group.name, start, end)
        closed = [t for t in trades if t.status == "closed"]
        profit = round(sum(t.profit or 0.0 for t in closed), 2)
        lines.append(f"{group.name}: {len(trades)} עסקאות, {len(closed)} סגורות, סה\"כ {profit}")

    ok = mailer.send(
        subject=f"דוח {year:04d}-{month:02d} — gold-signal-bot",
        body="\n".join(lines),
        attachments=paths,
    )
    print("\nנשלח בהצלחה." if ok else "\nהשליחה נכשלה. ראה את הלוג למעלה.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
