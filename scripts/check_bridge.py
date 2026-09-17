"""בדיקת הגשר מול GoldSignalBridge.mq5. הרץ:  py scripts\\check_bridge.py

מוצא את תיקיית Common\\Files של MT5, בודק שה-EA חי ומדפיס את מה
שצריך להיכנס ל-config.yaml.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

COMMON = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal" / "Common" / "Files"


def read_config_dir() -> str:
    try:
        from src.config import load_config

        return load_config().common_files_dir
    except Exception as exc:
        print(f"(לא הצלחתי לקרוא את config.yaml: {exc})")
        return ""


def main() -> int:
    configured = read_config_dir()
    target = Path(configured) if configured else COMMON

    print("=" * 62)
    print(f"תיקיית Common\\Files הצפויה : {COMMON}")
    print(f"מה שמוגדר ב-config.yaml     : {configured or '(ריק)'}")
    print(f"נבדק בפועל                  : {target}")
    print("=" * 62)

    if not target.exists():
        print("\n!! התיקייה לא קיימת.")
        print("   ב-MT5: File > Open Data Folder, עלה תיקייה אחת ל-Terminal,")
        print("   ואז Common\\Files. זו התיקייה שצריכה להיכנס ל-config.yaml.")
        return 1

    heartbeat = target / "gs_heartbeat.txt"
    if not heartbeat.exists():
        print("\n!! אין gs_heartbeat.txt - ה-EA לא רץ.")
        print("   צרף את GoldSignalBridge לגרף XAUUSD.m וודא שהסמיילי בפינה מחייך.")
        return 1

    age = time.time() - heartbeat.stat().st_mtime
    status = "חי" if age < 10 else f"ישן! עודכן לפני {int(age)} שניות"
    print(f"\ngs_heartbeat.txt : {status}")
    if age >= 10:
        print("   ה-EA מצורף אבל לא פועל. בדוק ש-Algo Trading ירוק ושהסמיילי מחייך.")
        return 1

    tick = target / "gs_tick.txt"
    if tick.exists():
        print(f"gs_tick.txt      : {tick.read_text(errors='replace').strip()}")

    positions = target / "gs_positions.txt"
    if positions.exists():
        lines = [ln for ln in positions.read_text(errors="replace").splitlines() if ln.strip()]
        print(f"פוזיציות פתוחות  : {len(lines)}")
        for line in lines:
            print(f"   {line}")

    print("\n" + "=" * 62)
    print("הגשר עובד. ודא שב-config.yaml רשום:")
    print("  broker:")
    print("    type: file_bridge")
    # גרשיים בודדים חובה: ב-YAML עם גרשיים כפולים הרצף \U נחשב escape ושובר את הקובץ.
    print(f"    common_files_dir: '{str(target)}'")
    print("  dry_run: false      (וגם DRY_RUN=false ב-.env)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
