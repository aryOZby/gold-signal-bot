"""אבחון חיבור MT5. הרץ על ה-VPS:  py scripts\\diag_mt5.py"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

try:
    import MetaTrader5 as mt5
except ImportError:
    raise SystemExit("חסר MetaTrader5. הרץ: py -m pip install MetaTrader5")


def is_elevated() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def running_terminals() -> list[str]:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq terminal64.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=20,
        ).stdout
    except Exception as exc:  # pragma: no cover - diagnostics only
        return [f"tasklist failed: {exc}"]
    return [line for line in out.splitlines() if "terminal64" in line.lower()]


def discover_terminals() -> list[str]:
    roots = [
        Path(r"C:\Program Files"),
        Path(r"C:\Program Files (x86)"),
        Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal",
    ]
    found: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        try:
            found.extend(str(p) for p in root.rglob("terminal64.exe"))
        except OSError:
            continue
    return found


def report_gold_symbols() -> Optional[str]:
    """אחרי חיבור מוצלח: אילו סימולי זהב קיימים ומה הבוט יבחר.

    מחזיר הודעת בעיה, או None אם הסימול תקין.
    """
    override = ""
    try:
        sys.path.insert(0, str(ROOT))
        from src.config import load_config

        override = load_config().symbol_override
    except Exception as exc:
        print(f"  (לא הצלחתי לקרוא את config.yaml: {exc})")

    all_symbols = mt5.symbols_get() or []
    gold = [s.name for s in all_symbols if "XAU" in s.name.upper() or "GOLD" in s.name.upper()]
    print(f"  סימולי זהב אצל הברוקר ({len(gold)}): {', '.join(gold) if gold else 'לא נמצאו'}")
    print(f"  symbol_override ב-config.yaml: {override or '(ריק - ישתמש בסימול מההודעה)'}")

    target = override or "XAUUSD"
    if gold and target not in gold:
        suggestion = next((s for s in gold if s.upper().startswith("XAUUSD")), gold[0])
        print(f"  !! '{target}' לא קיים אצל הברוקר.")
        return f"symbol_override='{target}' לא קיים. שנה ב-config.yaml ל-'{suggestion}'."

    if not mt5.symbol_select(target, True):
        return f"symbol_select נכשל עבור {target}: {mt5.last_error()}"
    info = mt5.symbol_info(target)
    tick = mt5.symbol_info_tick(target)
    if info is None or tick is None:
        return f"אין נתוני מחיר עבור {target}"
    print(f"  {target}: bid={tick.bid} ask={tick.ask} digits={info.digits} point={info.point}")
    print(f"     נפח: min={info.volume_min} max={info.volume_max} step={info.volume_step}")
    print(f"     trade_mode={info.trade_mode} (0=disabled, 4=full)  stops_level={info.trade_stops_level}")
    if int(getattr(info, "trade_mode", 4)) == 0:
        return f"המסחר בסימול {target} מושבת אצל הברוקר (trade_mode=0)."
    return None


def terminal_logs(tail: int = 30) -> list[str]:
    """MT5 writes auth + API-rejection lines to %APPDATA%\\MetaQuotes\\Terminal\\<id>\\logs."""
    base = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal"
    if not base.exists():
        return ["  לא נמצאה תיקיית לוגים של MetaQuotes"]
    logs: list[Path] = []
    for folder in base.iterdir():
        log_dir = folder / "logs"
        if log_dir.is_dir():
            logs.extend(log_dir.glob("*.log"))
    if not logs:
        return ["  לא נמצאו קבצי לוג"]
    newest = max(logs, key=lambda p: p.stat().st_mtime)
    text = ""
    for encoding in ("utf-16", "utf-8", "cp1255"):
        try:
            text = newest.read_text(encoding=encoding, errors="strict")
            break
        except (UnicodeError, OSError):
            continue
    if not text:
        text = newest.read_text(encoding="utf-8", errors="replace")
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    return [f"  קובץ: {newest}"] + [f"  {ln}" for ln in lines[-tail:]]


def attempt(label: str, **kwargs) -> bool:
    mt5.shutdown()
    ok = mt5.initialize(**kwargs)
    err = mt5.last_error()
    print(f"  {label}: {ok}  {err if not ok else ''}")
    if not ok:
        return False
    term = mt5.terminal_info()
    acct = mt5.account_info()
    print(f"     terminal connected={getattr(term, 'connected', None)} "
          f"trade_allowed={getattr(term, 'trade_allowed', None)} "
          f"path={getattr(term, 'path', None)}")
    if acct is None:
        print(f"     account_info=None  {mt5.last_error()}  <-- הטרמינל לא מחובר לחשבון מסחר")
        return False
    print(f"     account={acct.login} server={acct.server} balance={acct.balance} "
          f"margin_mode={acct.margin_mode} (2=hedging)")
    return True


def main() -> None:
    print("=" * 62)
    print(f"MetaTrader5 package : {mt5.__version__}")
    print(f"Python              : {sys.version.split()[0]} ({8 * ctypes.sizeof(ctypes.c_void_p)}bit)")
    print(f"Running as Admin    : {is_elevated()}")
    print("=" * 62)

    procs = running_terminals()
    print("terminal64.exe רץ כרגע:")
    for line in procs or ["  אין! פתח את JustMarkets MetaTrader 5 והתחבר לחשבון."]:
        print(f"  {line}")

    print("\nנתיבים שנמצאו בדיסק:")
    for p in discover_terminals() or ["  לא נמצא terminal64.exe"]:
        print(f"  {p}")

    env_path = os.getenv("MT5_TERMINAL_PATH") or ""
    login = os.getenv("MT5_LOGIN") or ""
    password = os.getenv("MT5_PASSWORD") or ""
    server = os.getenv("MT5_SERVER") or ""
    print("\n.env:")
    print(f"  MT5_TERMINAL_PATH = {env_path or '(ריק)'}")
    print(f"  MT5_LOGIN         = {login or '(ריק)'}")
    print(f"  MT5_SERVER        = {server or '(ריק)'}")
    print(f"  MT5_PASSWORD      = {'*' * len(password) if password else '(ריק)'}")
    if env_path and not Path(env_path).exists():
        print("  !! הנתיב ב-MT5_TERMINAL_PATH לא קיים")

    print("\nניסיונות התחברות:")
    paths = [p for p in [env_path, *discover_terminals()] if p]
    ok = attempt("initialize()", timeout=60000)
    for path in paths:
        if ok:
            break
        ok = attempt(f"initialize(path={Path(path).parent.name})", path=path, timeout=60000)
    if not ok and login and password and server:
        for path in paths or [None]:
            kwargs = {"login": int(login), "password": password, "server": server}
            if path:
                kwargs["path"] = path
            ok = attempt("initialize(+login/password/server)", timeout=60000, **kwargs)
            if ok:
                break

    problems: list[str] = []
    if ok:
        term = mt5.terminal_info()
        # החיבור יכול להצליח בזמן שהמסחר עצמו חסום, ואז כל פקודה תידחה.
        if term is not None and not getattr(term, "trade_allowed", True):
            problems.append(
                "trade_allowed=False - המסחר חסום בטרמינל. ב-MT5: Tools > Options >\n"
                "     Expert Advisors: לסמן 'Allow algorithmic trading' ולבטל את\n"
                "     'Disable automated trading via external Python API', ואז לוודא\n"
                "     שכפתור Algo Trading בסרגל ירוק."
            )
        print("\nבדיקת סימול הזהב:")
        symbol_problem = report_gold_symbols()
        if symbol_problem:
            problems.append(symbol_problem)

    print("\nלוג הטרמינל (סוף הקובץ):")
    for line in terminal_logs():
        print(line)

    print("\n" + "=" * 62)
    if ok and not problems:
        print("הכל תקין. אפשר להריץ:  py main.py")
    elif ok:
        print(f"החיבור עובד, אבל {len(problems)} דברים ימנעו ביצוע פקודות:")
        for num, problem in enumerate(problems, start=1):
            print(f"  {num}. {problem}")
    else:
        print("נכשל. החשוד המרכזי כש-(-6) חוזר מיד (ולא IPC timeout):")
        print("  1. ב-MT5: Tools > Options > Expert Advisors")
        print("     X  Disable automated trading via external Python API  <-- להוריד את הסימון")
        print("     V  Allow algorithmic trading")
        print("     אחרי השינוי: סגור את MT5 לגמרי ופתח מחדש.")
        print("  2. ודא ש-MT5 מחובר לחשבון מסחר - למטה מימין קצב נתונים, לא 'No connection'.")
        print("  3. מלא MT5_PASSWORD ו-MT5_SERVER ב-.env (השרת בדיוק כפי שמופיע בחלון הלוגין).")
    mt5.shutdown()


if __name__ == "__main__":
    main()
