"""מחליף את GoldSignalBridge בכל תיקיות ה-MT5 ומהדר אותו.

הרצה ב-VPS:
    py scripts\\vps\\install_ea.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "mt5" / "GoldSignalBridge.mq5"
APP = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal"
EDITORS = [
    Path(r"C:\Program Files\JustMarkets MetaTrader 5\metaeditor64.exe"),
    Path(r"C:\Program Files\MetaTrader 5\metaeditor64.exe"),
]
TERMINALS = [
    Path(r"C:\Program Files\JustMarkets MetaTrader 5\terminal64.exe"),
    Path(r"C:\Program Files\MetaTrader 5\terminal64.exe"),
]


def experts_dirs() -> list[Path]:
    found: list[Path] = []
    if APP.exists():
        for folder in APP.iterdir():
            experts = folder / "MQL5" / "Experts"
            if experts.is_dir():
                found.append(experts)
    for extra in (
        Path(r"C:\Program Files\JustMarkets MetaTrader 5\MQL5\Experts"),
        Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal" / "Common" / "Files",
    ):
        if extra.is_dir():
            found.append(extra)
    return found


def first_inputs(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"(לא נקרא: {exc})"
    lines = [ln.strip() for ln in text.splitlines() if "input " in ln or "version" in ln]
    return " | ".join(lines[:8]) or "(אין שורות input)"


def main() -> int:
    if not SRC.exists():
        print(f"חסר הקובץ החדש: {SRC}")
        print("הרץ קודם:  git pull")
        return 1

    print(f"מקור: {SRC}")
    print(f"  {first_inputs(SRC)}")
    if "InpLot" not in SRC.read_text(encoding="utf-8", errors="replace"):
        print("!! בקובץ המקור אין InpLot. git pull לא הצליח.")
        return 1

    print("\nסוגר את MT5...")
    subprocess.run(["taskkill", "/IM", "terminal64.exe", "/F"], capture_output=True)
    subprocess.run(["taskkill", "/IM", "metaeditor64.exe", "/F"], capture_output=True)
    time.sleep(2)

    print("\nעותקים שנמצאו לפני ההחלפה:")
    targets = experts_dirs()
    existing = []
    for folder in targets:
        for name in ("GoldSignalBridge.mq5", "GoldSignalBridge.ex5"):
            path = folder / name
            if path.exists():
                existing.append(path)
                print(f"  {path}")
                if path.suffix == ".mq5":
                    print(f"     {first_inputs(path)}")

    if not existing:
        print("  (לא נמצא עותק ישן — נעתיק לתיקיות Experts הקיימות)")

    copied = []
    for folder in targets:
        if folder.name == "Files":
            continue
        dest = folder / "GoldSignalBridge.mq5"
        dest.write_bytes(SRC.read_bytes())
        old_ex5 = folder / "GoldSignalBridge.ex5"
        if old_ex5.exists():
            try:
                old_ex5.unlink()
            except OSError as exc:
                print(f"  לא הצלחתי למחוק {old_ex5}: {exc}")
        copied.append(dest)
        print(f"הועתק -> {dest}")
        print(f"     {first_inputs(dest)}")

    editor = next((p for p in EDITORS if p.exists()), None)
    if editor is None:
        print("\n!! לא נמצא metaeditor64.exe — ההעתקה נעשתה, הדר ידנית ב-F7")
    else:
        print(f"\nמהדר: {editor}")
        for dest in copied:
            print(f"  compile {dest}")
            subprocess.run([str(editor), f"/compile:{dest}"], check=False)
            time.sleep(1)
            ex5 = dest.with_suffix(".ex5")
            print(f"     ex5 exists={ex5.exists()} size={ex5.stat().st_size if ex5.exists() else 0}")

    terminal = next((p for p in TERMINALS if p.exists()), None)
    if terminal is not None:
        print(f"\nפותח MT5: {terminal}")
        try:
            os.startfile(str(terminal))  # type: ignore[attr-defined]
        except AttributeError:
            subprocess.Popen([str(terminal)])
    print("\nעכשיו ב-MT5: הסר את ה-EA מהגרף (אם נשאר), גרור מחדש.")
    print("בכותרת חייב להיות 1.10 ובקלטים: Lot / Dry run / Magics.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
