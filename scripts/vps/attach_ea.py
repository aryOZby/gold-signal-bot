"""מצמיד את GoldSignalBridge לגרפי זהב בלי עכבר.

סוגר MT5 אם הוא פתוח, כותב default.tpl ומזריק את ה-EA לקבצי הגרף
השמורים. RoboForex -> Technical Pips. JustMarkets (.speed) -> profit_kings.

הרצה ב-VPS (אחרי git pull, ועדיף אחרי compile):
    py scripts\\vps\\attach_ea.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

APP = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal"
TERMINALS = [
    Path(r"C:\Program Files\MetaTrader 5\terminal64.exe"),
    Path(r"C:\Program Files\MetaTrader 5.speed\terminal64.exe"),
]
EXPERT_RE = re.compile(r"<expert>.*?</expert>\s*", re.DOTALL | re.IGNORECASE)
GOLD_RE = re.compile(r"XAU|GOLD", re.IGNORECASE)


def _inputs(*, vip: bool, pips: bool, kings: bool, lot_pips: str, lot_kings: str) -> str:
    def b(v: bool) -> str:
        return "true" if v else "false"

    return (
        f"InpListenVip={b(vip)}\n"
        f"InpLotVip=0.01\n"
        f"InpListenPips={b(pips)}\n"
        f"InpLotPips={lot_pips}\n"
        f"InpListenProfitKings={b(kings)}\n"
        f"InpLotProfitKings={lot_kings}\n"
        "InpDryRun=false\n"
        "InpMagicList=260908,260909,260910\n"
        "InpTimerMs=50\n"
        "InpDeviation=30\n"
    )


def _preset(origin: str) -> tuple[str, str]:
    text = origin.lower()
    if "speed" in text or "justmarkets" in text:
        label = "profit_kings / JustMarkets demo"
        body = _inputs(vip=False, pips=False, kings=True, lot_pips="0.01", lot_kings="0.01")
    else:
        label = "Technical Pips / RoboForex live"
        body = _inputs(vip=False, pips=True, kings=False, lot_pips="0.05", lot_kings="0.01")
    return label, body


def _expert_block(inputs: str) -> str:
    return (
        "<expert>\n"
        "name=GoldSignalBridge\n"
        "flags=343\n"
        "window_num=0\n"
        "<inputs>\n"
        f"{inputs}"
        "</inputs>\n"
        "</expert>\n"
    )


def _default_tpl(inputs: str, symbol: str) -> str:
    return (
        "<chart>\n"
        f"symbol={symbol}\n"
        "period=16385\n"
        "leftpos=0\n"
        "digits=2\n"
        "scale=8\n"
        "graph=1\n"
        "fore=0\n"
        "grid=1\n"
        "volume=0\n"
        "scroll=1\n"
        "shift=1\n"
        "ohlc=1\n"
        "one_click=0\n"
        "askline=0\n"
        "days=0\n"
        "descriptions=0\n"
        "shift_size=20\n"
        "fixed_pos=0\n"
        "window_left=0\n"
        "window_top=0\n"
        "window_right=800\n"
        "window_bottom=500\n"
        "window_type=3\n"
        "background_color=0\n"
        "foreground_color=16777215\n"
        "barup_color=65280\n"
        "bardown_color=255\n"
        "bullcandle_color=0\n"
        "bearcandle_color=16777215\n"
        "chartline_color=65280\n"
        "volumes_color=3329330\n"
        "grid_color=10061943\n"
        "askline_color=255\n"
        "stops_color=255\n"
        "\n"
        "<window>\n"
        "height=100\n"
        "fixed_height=0\n"
        "<indicator>\n"
        "name=Main\n"
        "path=\n"
        "apply=1\n"
        "show_data=1\n"
        "scale_inherit=0\n"
        "scale_line=0\n"
        "scale_line_percent=50\n"
        "scale_line_value=0.000000\n"
        "scale_fixmin=0\n"
        "scale_fixmin_val=0.000000\n"
        "scale_fixmax=0\n"
        "scale_fixmax_val=0.000000\n"
        "expertmode=0\n"
        "fixed_height=-1\n"
        "</indicator>\n"
        f"{_expert_block(inputs)}"
        "</window>\n"
        "</chart>\n"
    )


def _inject(text: str, expert: str) -> str:
    if EXPERT_RE.search(text):
        return EXPERT_RE.sub(expert, text, count=1)
    marker = "</window>"
    if marker in text:
        return text.replace(marker, expert + marker, 1)
    return text.rstrip() + "\n" + expert


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-16")


def _origin(folder: Path) -> str:
    path = folder / "origin.txt"
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-16", errors="replace")
    except OSError:
        return path.read_text(encoding="utf-8", errors="replace")


def _chart_files(folder: Path) -> list[Path]:
    charts = folder / "MQL5" / "Profiles" / "Charts"
    if not charts.is_dir():
        return []
    return [p for p in charts.rglob("*.chr") if p.is_file()]


def apply_to_terminals(*, kill: bool = True, start: bool = True) -> int:
    if not APP.exists():
        print(f"לא נמצא {APP}")
        return 1

    if kill:
        print("סוגר את MT5 כדי שאפשר יהיה לכתוב לקבצי הגרף...")
        subprocess.run(["taskkill", "/IM", "terminal64.exe", "/F"], capture_output=True)
        subprocess.run(["taskkill", "/IM", "metaeditor64.exe", "/F"], capture_output=True)
        time.sleep(2)

    written = 0
    for folder in sorted(APP.iterdir()):
        if not folder.is_dir() or folder.name.lower() == "common":
            continue
        experts = folder / "MQL5" / "Experts"
        if not experts.is_dir():
            continue
        origin = _origin(folder)
        if not origin.strip():
            continue
        label, inputs = _preset(origin)
        expert = _expert_block(inputs)
        symbol = "XAUUSD.m" if ("speed" in origin.lower() or "justmarkets" in origin.lower()) else "XAUUSD"
        tpl = _default_tpl(inputs, symbol)
        print(f"\n{folder.name}")
        print(f"  origin: {origin.strip().splitlines()[0]}")
        print(f"  preset: {label}")

        for rel in ("templates/default.tpl", "MQL5/Profiles/Templates/default.tpl"):
            path = folder / rel
            _write(path, tpl)
            print(f"  tpl -> {path}")
            written += 1

        for chart in _chart_files(folder):
            raw = chart.read_bytes()
            try:
                text = raw.decode("utf-16")
                enc = "utf-16"
            except UnicodeDecodeError:
                text = raw.decode("utf-8", errors="replace")
                enc = "utf-8"
            if not GOLD_RE.search(text) and "symbol=" in text.lower():
                continue
            if not GOLD_RE.search(text):
                continue
            chart.write_text(_inject(text, expert), encoding=enc)
            print(f"  chart -> {chart}")
            written += 1

    if written == 0:
        print("לא נמצאו תיקיות טרמינל לכתיבה.")
        return 1

    if start:
        print()
        for terminal in TERMINALS:
            if not terminal.exists():
                continue
            print(f"פותח MT5: {terminal}")
            try:
                os.startfile(str(terminal))  # type: ignore[attr-defined]
            except AttributeError:
                subprocess.Popen([str(terminal)])
            time.sleep(2)
    print("\nכשהחלון נפתח: בכותרת הגרף צריך להיות GoldSignalBridge.")
    print("F7 רק אם רוצים לשנות לוט. לא צריך קליק ימני ולא גרירה.")
    return 0


def main() -> int:
    return apply_to_terminals(kill=True, start=True)


if __name__ == "__main__":
    sys.exit(main())
