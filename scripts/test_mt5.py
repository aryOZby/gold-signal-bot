"""Find why MT5 Python API returns -6. Run on the VPS:  py scripts\\test_mt5.py"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

try:
    import MetaTrader5 as mt5
except ImportError:
    raise SystemExit("pip install MetaTrader5")


def main() -> None:
    print("login", os.getenv("MT5_LOGIN"))
    print("server", os.getenv("MT5_SERVER"))
    print("path", os.getenv("MT5_TERMINAL_PATH"))
    print("initialize()", mt5.initialize(timeout=60000), mt5.last_error())
    print("terminal", mt5.terminal_info())
    print("account", mt5.account_info())
    mt5.shutdown()


if __name__ == "__main__":
    main()
