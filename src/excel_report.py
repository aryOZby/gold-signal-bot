from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import SignalRecord, TradeRecord
from .parser import parse_signal
from .stats import build_stats, max_tp_hit
from .timeutil import display_dt

_LOG = logging.getLogger(__name__)

HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(color="FFFFFF", bold=True)
WRAP = Alignment(wrap_text=True, vertical="center")

TRADE_HEADERS = [
    "קבוצה",
    "מזהה טלגרם",
    "יוזרניים טלגרם",
    "מזהה איתות",
    "תאריך ושעה קבלת איתות",
    "סימול",
    "כיוון",
    "טווח כניסה",
    "מספר TP",
    "מחיר TP",
    "סדר בין הנלקחות",
    "האם ה-TP ניקלח",
    "טיקט",
    "לוט",
    "תאריך ושעה כניסה",
    "מחיר כניסה",
    "סטופ",
    "סטופ הועבר לכניסה",
    "תאריך ושעה יציאה / מימוש",
    "מחיר יציאה",
    "סיבת יציאה",
    "רווח/הפסד",
    "פיפס",
    "סטטוס",
]

SIGNAL_HEADERS = [
    "מזהה איתות",
    "קבוצה",
    "מזהה טלגרם",
    "יוזרניים טלגרם",
    "תאריך ושעה קבלה",
    "סימול",
    "כיוון",
    "טווח",
    "SL",
    "סטטוס",
    "TP מקסימלי שנלקח",
    "כניסה ראשונה",
    "יציאה אחרונה",
    "תאריך ושעה סיום",
    "סיבת דילוג",
]

REASON_HE = {
    "TP": "טייק פרופיט",
    "SL": "סטופ לוס",
    "BREAKEVEN": "איזון (כניסה)",
    "SAFETY": "מנגנון בטיחות",
    "MANUAL": "ידני",
    "UNKNOWN": "לא ידוע",
}

STATUS_HE = {
    "open": "פתוח",
    "closed": "סגור",
    "failed": "נכשל",
    "active": "פעיל",
    "completed": "הושלם",
    "skipped": "דולג",
}


class ExcelReporter:
    def __init__(self, output_dir: Path, tz: ZoneInfo):
        self.output_dir = output_dir
        self.tz = tz
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def month_path(self, group_name: str, year: int, month: int, final: bool = False) -> Path:
        folder = self.output_dir / safe_group_folder(group_name)
        folder.mkdir(parents=True, exist_ok=True)
        suffix = "_final" if final else ""
        return folder / f"{safe_group_folder(group_name)}_{year:04d}-{month:02d}{suffix}.xlsx"

    def write_month(
        self,
        group_name: str,
        year: int,
        month: int,
        signals: list[SignalRecord],
        trades: list[TradeRecord],
        final: bool = False,
    ) -> Path:
        signals, trades = isolate_group(group_name, signals, trades)
        path = self.month_path(group_name, year, month, final=final)
        wb = Workbook()
        ws_trades = wb.active
        ws_trades.title = "עסקאות"
        self._write_trades(ws_trades, trades)

        ws_detail = wb.create_sheet("פירוט איתות")
        self._write_signal_detail(ws_detail, signals, trades)

        ws_signals = wb.create_sheet("איתותים")
        self._write_signals(ws_signals, signals, trades)

        ws_stats = wb.create_sheet("סטטיסטיקה")
        self._write_stats(ws_stats, group_name, year, month, signals, trades)

        ws_daily = wb.create_sheet("סיכום יומי")
        self._write_daily(ws_daily, trades)

        for ws in wb.worksheets:
            ws.sheet_view.rightToLeft = True
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions

        wb.save(path)
        return path

    def _write_trades(self, ws, trades: list[TradeRecord]) -> None:
        _header(ws, TRADE_HEADERS)
        ranks = _taken_rank(trades)
        for i, t in enumerate(trades, start=2):
            reason = t.close_reason or ""
            if t.sl_moved_to_be and (reason or "").upper() == "SL":
                reason = "BREAKEVEN"
            hit = _tp_was_hit(t)
            ws.cell(i, 1, t.group_name)
            ws.cell(i, 2, t.telegram_chat_id or "")
            ws.cell(i, 3, t.telegram_username)
            ws.cell(i, 4, t.signal_id)
            ws.cell(i, 5, display_dt(t.received_at, self.tz))
            ws.cell(i, 6, t.symbol)
            ws.cell(i, 7, t.side)
            ws.cell(i, 8, f"{t.zone_low:g}-{t.zone_high:g}")
            ws.cell(i, 9, t.tp_index)
            ws.cell(i, 10, t.tp_price)
            ws.cell(i, 11, ranks.get((t.signal_id, t.tp_index), ""))
            ws.cell(i, 12, hit)
            ws.cell(i, 13, t.ticket)
            ws.cell(i, 14, t.lot)
            ws.cell(i, 15, display_dt(t.entry_time, self.tz) or ("—" if t.status != "open" else "ממתין"))
            ws.cell(i, 16, t.entry_price)
            ws.cell(i, 17, t.sl)
            ws.cell(i, 18, "כן" if t.sl_moved_to_be else "לא")
            ws.cell(i, 19, display_dt(t.exit_time, self.tz) or ("—" if t.status == "open" else ""))
            ws.cell(i, 20, t.exit_price)
            ws.cell(i, 21, REASON_HE.get(reason.upper(), reason) if reason else ("פתוח" if t.status == "open" else ""))
            ws.cell(i, 22, t.profit)
            ws.cell(i, 23, t.pips)
            ws.cell(i, 24, STATUS_HE.get(t.status, t.status))
        _autosize(ws, TRADE_HEADERS)

    def _write_signals(self, ws, signals: list[SignalRecord], trades: list[TradeRecord]) -> None:
        _header(ws, SIGNAL_HEADERS)
        by_sig: dict[str, list[TradeRecord]] = defaultdict(list)
        for t in trades:
            by_sig[t.signal_id].append(t)
        for i, s in enumerate(signals, start=2):
            legs = by_sig.get(s.id, [])
            level = s.max_tp_hit
            if level is None:
                level = max_tp_hit(legs)
            ws.cell(i, 1, s.id)
            ws.cell(i, 2, s.group_name)
            ws.cell(i, 3, s.chat_id or "")
            ws.cell(i, 4, s.username)
            ws.cell(i, 5, display_dt(s.received_at, self.tz))
            ws.cell(i, 6, s.symbol)
            ws.cell(i, 7, s.side)
            ws.cell(i, 8, f"{s.zone_low:g}-{s.zone_high:g}")
            ws.cell(i, 9, s.sl)
            ws.cell(i, 10, STATUS_HE.get(s.status, s.status))
            ws.cell(i, 11, level)
            ws.cell(i, 12, display_dt(_first_entry(legs), self.tz))
            ws.cell(i, 13, display_dt(_last_exit(legs), self.tz))
            ws.cell(i, 14, display_dt(s.completed_at, self.tz))
            ws.cell(i, 15, s.skipped_reason)
        _autosize(ws, SIGNAL_HEADERS)

    def _write_signal_detail(self, ws, signals: list[SignalRecord], trades: list[TradeRecord]) -> None:
        by_sig: dict[str, list[TradeRecord]] = defaultdict(list)
        for t in trades:
            by_sig[t.signal_id].append(t)
        max_levels = 0
        parsed_tps: dict[str, tuple[float, ...]] = {}
        for s in signals:
            tps = _signal_tps(s)
            parsed_tps[s.id] = tps
            max_levels = max(max_levels, len(tps), max((t.tp_index for t in by_sig.get(s.id, [])), default=0))
        headers = [
            "מזהה איתות",
            "קבוצה",
            "תאריך ושעה קבלת איתות",
            "כיוון",
            "טווח",
            "SL",
            "סטטוס איתות",
            "פוזיציות שנלקחו",
            "סיכום TP",
            "כניסה ראשונה",
            "יציאה אחרונה",
        ]
        headers.extend(f"TP{n}" for n in range(1, max_levels + 1))
        _header(ws, headers)
        for i, s in enumerate(signals, start=2):
            legs = by_sig.get(s.id, [])
            by_index = {t.tp_index: t for t in legs}
            tps = parsed_tps.get(s.id) or ()
            levels = max(len(tps), max(by_index, default=0))
            summary = _tp_summary(levels, by_index)
            taken = [t for t in legs if t.status != "failed"]
            ws.cell(i, 1, s.id)
            ws.cell(i, 2, s.group_name)
            ws.cell(i, 3, display_dt(s.received_at, self.tz))
            ws.cell(i, 4, s.side)
            ws.cell(i, 5, f"{s.zone_low:g}-{s.zone_high:g}")
            ws.cell(i, 6, s.sl)
            ws.cell(i, 7, STATUS_HE.get(s.status, s.status))
            ws.cell(i, 8, len(taken))
            ws.cell(i, 9, summary)
            ws.cell(i, 10, display_dt(_first_entry(taken), self.tz))
            ws.cell(i, 11, display_dt(_last_exit(legs), self.tz))
            for n in range(1, max_levels + 1):
                cell = ws.cell(i, 11 + n, describe_tp_leg(n, by_index.get(n), self.tz))
                cell.alignment = WRAP
            ws.row_dimensions[i].height = 90
        _autosize(ws, headers)
        for n in range(1, max_levels + 1):
            ws.column_dimensions[get_column_letter(11 + n)].width = 36

    def _write_stats(
        self,
        ws,
        group_name: str,
        year: int,
        month: int,
        signals: list[SignalRecord],
        trades: list[TradeRecord],
    ) -> None:
        stats = build_stats(signals, trades)
        rows = [
            ("קבוצה", group_name),
            ("חודש", f"{year:04d}-{month:02d}"),
            ("סה״כ איתותים", stats["signals_total"]),
            ("הושלמו", stats["signals_completed"]),
            ("פעילים", stats["signals_active"]),
            ("דולגו (עסוק / כפול)", stats["signals_skipped"]),
            ("נכשלו", stats["signals_failed"]),
            ("עסקאות בגיליון (1:1 מול הדאטה)", len(trades)),
            ("פוזיציות שנלקחו", len([t for t in trades if t.status != "failed"])),
            ("נסגרו בטייק", len([t for t in trades if t.status == "closed" and (t.close_reason or "").upper() == "TP"])),
            ("רווח/הפסד כולל", stats["profit_total"]),
            ("ממוצע לאיתות שהושלם", stats["profit_avg"]),
            ("", ""),
            (
                "אחוזי פגיעה בטייקים (מתוך איתותים שהושלמו)",
                f"n={stats['denominator']}",
            ),
        ]
        _header(ws, ["מדד", "ערך"])
        r = 2
        for label, value in rows:
            ws.cell(r, 1, label)
            ws.cell(r, 2, value)
            r += 1
        r += 1
        ws.cell(r, 1, "TP")
        ws.cell(r, 2, "כמה איתותים הגיעו לפחות עד כאן")
        ws.cell(r, 3, "אחוז")
        for cell in (ws.cell(r, 1), ws.cell(r, 2), ws.cell(r, 3)):
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
        r += 1
        for n in range(1, stats["max_tp_levels"] + 1):
            ws.cell(r, 1, f"TP{n}")
            ws.cell(r, 2, stats["hit_counts"].get(n, 0))
            ws.cell(r, 3, f"{stats['hit_pct'].get(n, 0)}%")
            r += 1
        r += 2
        ws.cell(r, 1, "התפלגות TP מקסימלי שנלקח")
        r += 1
        ws.cell(r, 1, "TP מקסימלי")
        ws.cell(r, 2, "מספר איתותים")
        ws.cell(r, 3, "אחוז")
        for cell in (ws.cell(r, 1), ws.cell(r, 2), ws.cell(r, 3)):
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
        r += 1
        for level, count in sorted(stats["distribution"].items()):
            label = "יציאה לפני TP1 (סטופ/אחר)" if level == 0 else f"TP{level}"
            ws.cell(r, 1, label)
            ws.cell(r, 2, count)
            ws.cell(r, 3, f"{stats['distribution_pct'].get(level, 0)}%")
            r += 1
        _autosize(ws, ["מדד", "ערך", "אחוז"])

    def _write_daily(self, ws, trades: list[TradeRecord]) -> None:
        headers = ["תאריך", "עסקאות", "סגורות", "רווח/הפסד", "פיפס"]
        _header(ws, headers)
        buckets: dict[str, list[TradeRecord]] = defaultdict(list)
        for t in trades:
            day = display_dt(t.received_at, self.tz)[:10]
            if day:
                buckets[day].append(t)
        for i, day in enumerate(sorted(buckets), start=2):
            group = buckets[day]
            closed = [t for t in group if t.status == "closed"]
            ws.cell(i, 1, day)
            ws.cell(i, 2, len(group))
            ws.cell(i, 3, len(closed))
            ws.cell(i, 4, round(sum(t.profit or 0.0 for t in closed), 2))
            ws.cell(i, 5, round(sum(t.pips or 0.0 for t in closed), 1))
        _autosize(ws, headers)


def _taken_rank(trades: list[TradeRecord]) -> dict[tuple[str, int], int]:
    by_sig: dict[str, list[TradeRecord]] = defaultdict(list)
    for trade in trades:
        if trade.status == "failed":
            continue
        by_sig[trade.signal_id].append(trade)
    ranks: dict[tuple[str, int], int] = {}
    for signal_id, group in by_sig.items():
        ordered = sorted(group, key=lambda t: t.tp_index)
        for i, trade in enumerate(ordered, start=1):
            ranks[(signal_id, trade.tp_index)] = i
    return ranks


def _tp_was_hit(trade: TradeRecord) -> str:
    if trade.status == "open":
        return "לא (פתוח)"
    if trade.status == "failed":
        return "לא (נכשל)"
    if (trade.close_reason or "").upper() == "TP":
        return "כן"
    return "לא"


def _first_entry(trades: list[TradeRecord]):
    times = [t.entry_time for t in trades if t.entry_time is not None]
    return min(times) if times else None


def _last_exit(trades: list[TradeRecord]):
    times = [t.exit_time for t in trades if t.exit_time is not None]
    return max(times) if times else None


def _signal_tps(signal: SignalRecord) -> tuple[float, ...]:
    if signal.tps:
        return tuple(signal.tps)
    if signal.raw_text:
        parsed = parse_signal(signal.raw_text)
        if parsed is not None:
            return parsed.tps
    return ()


def _tp_summary(levels: int, by_index: dict[int, TradeRecord]) -> str:
    taken: list[str] = []
    hit: list[str] = []
    open_legs: list[str] = []
    skipped: list[str] = []
    for n in range(1, levels + 1):
        trade = by_index.get(n)
        label = f"TP{n}"
        if trade is None or trade.status == "failed":
            skipped.append(label)
            continue
        taken.append(label)
        if trade.status == "open":
            open_legs.append(label)
        elif (trade.close_reason or "").upper() == "TP":
            hit.append(label)
    parts = []
    if taken:
        parts.append("נלקחו " + ", ".join(taken))
    if hit:
        parts.append("ניקלחו " + ", ".join(hit))
    if open_legs:
        parts.append("פתוחים " + ", ".join(open_legs))
    if skipped:
        parts.append("לא נלקחו " + ", ".join(skipped))
    return " | ".join(parts)


def describe_tp_leg(index: int, trade: Optional[TradeRecord], tz: ZoneInfo) -> str:
    if trade is None:
        return f"TP{index}: לא נלקח"
    if trade.status == "failed":
        return f"TP{index}: נלקח — נכשל בפתיחה"
    lines = [
        f"TP{index}: נלקח",
        f"מחיר יעד: {trade.tp_price:g}",
    ]
    if trade.ticket:
        lines.append(f"טיקט: {trade.ticket}")
    lines.append(f"כניסה: {display_dt(trade.entry_time, tz) or '—'}")
    if trade.entry_price is not None:
        lines.append(f"מחיר כניסה: {trade.entry_price:g}")
    if trade.status == "open":
        lines.append("ניקלח: לא (עדיין פתוח)")
        lines.append("יציאה: —")
    else:
        hit = (trade.close_reason or "").upper() == "TP"
        reason = (trade.close_reason or "").upper()
        if trade.sl_moved_to_be and reason == "SL":
            reason = "BREAKEVEN"
        lines.append(f"ניקלח: {'כן' if hit else 'לא'}")
        lines.append(f"יציאה: {display_dt(trade.exit_time, tz) or '—'}")
        if trade.exit_price is not None:
            lines.append(f"מחיר יציאה: {trade.exit_price:g}")
        if reason:
            lines.append(f"סיבה: {REASON_HE.get(reason, reason)}")
        if trade.profit is not None:
            lines.append(f"רווח/הפסד: {trade.profit}")
    return "\n".join(lines)


def month_bounds(year: int, month: int, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1, tzinfo=tz)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=tz)
    else:
        end = datetime(year, month + 1, 1, tzinfo=tz)
    return start, end


def _header(ws, headers: list[str]) -> None:
    for col, name in enumerate(headers, start=1):
        cell = ws.cell(1, col, name)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = WRAP


def _autosize(ws, headers: list[str]) -> None:
    for i, name in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(i)].width = max(14, min(36, len(name) + 4))


def safe_group_folder(name: str) -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", (name or "").strip(), flags=re.UNICODE)
    return cleaned.strip("._") or "group"


def isolate_group(
    group_name: str,
    signals: list[SignalRecord],
    trades: list[TradeRecord],
) -> tuple[list[SignalRecord], list[TradeRecord]]:
    sigs = [s for s in signals if s.group_name == group_name]
    trs = [t for t in trades if t.group_name == group_name]
    leaked = (len(signals) - len(sigs)) + (len(trades) - len(trs))
    if leaked:
        _LOG.warning(
            "Dropped %s rows that did not belong to group %s",
            leaked,
            group_name,
        )
    return sigs, trs
