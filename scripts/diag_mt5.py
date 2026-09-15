"""אבחון חיבור MT5. הרץ על ה-VPS:  py scripts\\diag_mt5.py"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path

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

    print("\n" + "=" * 62)
    if ok:
        print("הכל תקין. אפשר להריץ:  py main.py")
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
