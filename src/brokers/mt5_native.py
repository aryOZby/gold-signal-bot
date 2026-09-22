from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..models import BrokerPosition, ClosedDeal, CloseReason, OrderResult, Side
from ..timeutil import utcnow
from .base import Broker

_LOG = logging.getLogger(__name__)

try:
    import MetaTrader5 as mt5  # type: ignore
except ImportError:  # pragma: no cover - optional on macOS
    mt5 = None


_ACCOUNT_HEDGING = 2
_DEAL_ENTRY_OUT = 1


def _reason_from_deal(deal) -> CloseReason:
    reason = int(getattr(deal, "reason", -1))
    mapping = {
        3: CloseReason.SL,   # DEAL_REASON_SL
        4: CloseReason.TP,   # DEAL_REASON_TP
        5: CloseReason.MANUAL,  # DEAL_REASON_SO / stop-out treated as manual-ish
    }
    return mapping.get(reason, CloseReason.UNKNOWN)


class Mt5NativeBroker(Broker):
    def __init__(
        self,
        login: Optional[int] = None,
        password: str = "",
        server: str = "",
        path: str = "",
    ):
        if mt5 is None:
            raise RuntimeError(
                "החבילה MetaTrader5 זמינה רק ב-Windows. "
                "השתמש ב-file_bridge או dry_run במק, או הרץ את הבוט על VPS חלונות."
            )
        self.login = login
        self.password = password
        self.server = server
        self.path = path
        self._connected = False

    def connect(self) -> None:
        errors = []
        # קודם מתחברים לטרמינל שכבר פתוח ומחובר. shutdown()+path פותח
        # תהליך שני בלי לוגין ומחזיר -6 גם כשהחלון שאתה רואה תקין.
        for kwargs, shutdown_first in self._init_attempts():
            if shutdown_first:
                mt5.shutdown()
            ok = mt5.initialize(**kwargs)
            if not ok:
                errors.append((kwargs.get("path"), mt5.last_error()))
                continue
            if self.login and self.password and self.server:
                if not mt5.login(self.login, password=self.password, server=self.server):
                    errors.append((kwargs.get("path"), mt5.last_error()))
                    mt5.shutdown()
                    continue
            info = mt5.account_info()
            if info is None:
                errors.append((kwargs.get("path"), mt5.last_error() or "account_info failed"))
                mt5.shutdown()
                continue
            if int(getattr(info, "margin_mode", _ACCOUNT_HEDGING)) != _ACCOUNT_HEDGING:
                mt5.shutdown()
                raise RuntimeError(
                    "חשבון נטינג (netting) לא נתמך. האסטרטגיה דורשת חשבון גידור (hedging) "
                    "כדי לפתוח כמה פוזיציות על אותו סימול עם טייקים שונים."
                )
            self._connected = True
            if self.login and int(info.login) != int(self.login):
                _LOG.warning(
                    "MT5_LOGIN ב-.env הוא %s אבל הטרמינל מחובר ל-%s. "
                    "משתמשים בחשבון הפתוח.",
                    self.login,
                    info.login,
                )
            _LOG.info(
                "Connected to MT5 account %s server %s path=%s",
                info.login,
                info.server,
                kwargs.get("path") or "(attached)",
            )
            return
        raise RuntimeError(
            "MT5 initialize failed. בדוק לפי הסדר:\n"
            "  1. Journal של MT5 (Ctrl+T): השורה האחרונה של Network חייבת להיות\n"
            "     'authorized on ...' ולא 'Invalid account' / 'authorization failed'.\n"
            "     גרף פתוח לא מספיק — אם הדמו נדחה, Python יקבל -6.\n"
            "  2. File > Login to Trade Account עם דמו תקף (Master + השרת המדויק).\n"
            "  3. Tools > Options > Expert Advisors: לבטל את הסימון של\n"
            "     'Disable automated trading via external Python API'.\n"
            "  4. CMD ו-MT5 באותה רמת הרשאה (שניהם רגילים או שניהם כמנהל).\n"
            "  5. רוקן MT5_LOGIN ב-.env אם הוא מספר לייב והטרמינל בדמו.\n"
            "  לאבחון מלא:  py scripts\\diag_mt5.py\n"
            f"  Last errors: {errors[-3:]}"
        )

    def _init_attempts(self) -> list[tuple[dict, bool]]:
        """(kwargs, shutdown_first). הניסיון הראשון נצמד לטרמינל החי."""
        attempts: list[tuple[dict, bool]] = []
        attempts.append(({"timeout": 60_000}, False))
        paths: list[Optional[str]] = []
        if self.path:
            paths.append(self.path)
        paths.extend(_discover_terminals())
        paths.append(None)
        seen = {""}
        for path in paths:
            key = path or ""
            if key in seen:
                continue
            seen.add(key)
            base: dict = {"timeout": 60_000}
            if path:
                base["path"] = path
            if self.login and self.password and self.server:
                with_login = dict(base)
                with_login.update(
                    login=int(self.login),
                    password=self.password,
                    server=self.server,
                )
                attempts.append((with_login, True))
            attempts.append((dict(base), True))
        return attempts

    def shutdown(self) -> None:
        if self._connected and mt5 is not None:
            mt5.shutdown()
            self._connected = False

    def _ensure_connected(self) -> bool:
        """הטרמינל עלול להיסגר או להחליף חשבון תוך כדי ריצה."""
        if mt5.account_info() is not None:
            return True
        _LOG.warning("MT5 link is stale (%s) — reconnecting", mt5.last_error())
        self._connected = False
        try:
            self.connect()
        except Exception:
            _LOG.exception("MT5 reconnect failed")
            return False
        return self._connected

    def _describe_symbol_failure(self, symbol: str) -> str:
        """מסביר למה symbol_select נכשל במקום להחזיר הודעה סתומה."""
        error = mt5.last_error()
        info = mt5.account_info()
        account = f"account={info.login} server={info.server}" if info else "no account"
        available = [
            s.name
            for s in (mt5.symbols_get() or [])
            if "XAU" in s.name.upper() or "GOLD" in s.name.upper()
        ]
        if available and symbol not in available:
            return (
                f"symbol_select failed {symbol}: לא קיים בחשבון הנוכחי ({account}). "
                f"סימולי זהב זמינים: {', '.join(available)}. "
                f"עדכן את symbol_override ב-config.yaml."
            )
        return f"symbol_select failed {symbol}: {error} ({account})"

    def market_order(
        self,
        symbol: str,
        side: Side,
        volume: float,
        sl: float,
        tp: float,
        comment: str,
        deviation: int,
        magic: int,
    ) -> OrderResult:
        if not self._ensure_connected():
            return OrderResult(False, None, None, None, message="MT5 not connected")
        resolved = self._prepare_symbol(symbol)
        if resolved is None:
            return OrderResult(False, None, None, None, message=self._describe_symbol_failure(symbol))
        symbol = resolved
        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if info is None or tick is None:
            return OrderResult(False, None, None, None, message=f"no tick for {symbol}")

        sl_n = _normalize_price(sl, info)
        tp_n = _normalize_price(tp, info)
        order_type = mt5.ORDER_TYPE_BUY if side is Side.BUY else mt5.ORDER_TYPE_SELL
        price = tick.ask if side is Side.BUY else tick.bid
        request_base = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type,
            "price": price,
            "sl": sl_n,
            "tp": tp_n,
            "deviation": deviation,
            "magic": magic,
            "comment": comment[:31],
            "type_time": mt5.ORDER_TIME_GTC,
        }

        last = None
        for filling in _filling_candidates(info):
            request = dict(request_base)
            request["type_filling"] = filling
            result = mt5.order_send(request)
            last = result
            if result is None:
                continue
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                fill_price = float(result.price) or price
                return OrderResult(
                    ok=True,
                    ticket=int(result.order),
                    fill_price=fill_price,
                    fill_time=utcnow(),
                    retcode=int(result.retcode),
                    message=result.comment or "done",
                    sl=sl_n,
                    tp=tp_n,
                )
            if result.retcode != mt5.TRADE_RETCODE_INVALID_FILL:
                break

        retcode = int(last.retcode) if last is not None else None
        msg = last.comment if last is not None else str(mt5.last_error())
        return OrderResult(False, None, None, None, retcode=retcode, message=str(msg))

    def modify_sl_tp(self, ticket: int, sl: Optional[float], tp: Optional[float]) -> bool:
        pos = mt5.positions_get(ticket=ticket)
        if not pos:
            return False
        position = pos[0]
        info = mt5.symbol_info(position.symbol)
        new_sl = _normalize_price(sl, info) if sl is not None else position.sl
        new_tp = _normalize_price(tp, info) if tp is not None else position.tp
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": position.symbol,
            "position": ticket,
            "sl": new_sl,
            "tp": new_tp,
        }
        result = mt5.order_send(request)
        ok = result is not None and result.retcode == mt5.TRADE_RETCODE_DONE
        if not ok:
            _LOG.warning("modify SL/TP failed ticket=%s result=%s", ticket, result)
        return bool(ok)

    def positions(self, magic: int) -> list[BrokerPosition]:
        rows = mt5.positions_get()
        if not rows:
            return []
        out = []
        for p in rows:
            if int(p.magic) != magic:
                continue
            side = Side.BUY if p.type == mt5.ORDER_TYPE_BUY else Side.SELL
            out.append(
                BrokerPosition(
                    ticket=int(p.ticket),
                    symbol=p.symbol,
                    side=side,
                    volume=float(p.volume),
                    price_open=float(p.price_open),
                    sl=float(p.sl),
                    tp=float(p.tp),
                    profit=float(p.profit),
                    comment=p.comment or "",
                )
            )
        return out

    def closed_deal(self, ticket: int) -> Optional[ClosedDeal]:
        deals = mt5.history_deals_get(position=ticket)
        if not deals:
            now = datetime.now(timezone.utc)
            from_ts = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
            deals = mt5.history_deals_get(from_ts, now) or []
        exit_deals = [
            d
            for d in deals
            if int(getattr(d, "position_id", 0)) == ticket
            and int(getattr(d, "entry", 0)) == _DEAL_ENTRY_OUT
        ]
        if not exit_deals:
            exit_deals = [d for d in deals if int(getattr(d, "order", 0)) == ticket]
        if not exit_deals:
            return None
        deal = exit_deals[-1]
        ts = datetime.fromtimestamp(deal.time, tz=timezone.utc)
        profit = float(deal.profit) + float(getattr(deal, "swap", 0) or 0) + float(
            getattr(deal, "commission", 0) or 0
        )
        return ClosedDeal(
            ticket=ticket,
            exit_price=float(deal.price),
            exit_time=ts,
            profit=profit,
            reason=_reason_from_deal(deal),
        )

    def last_price(self, symbol: str) -> Optional[float]:
        resolved = self._prepare_symbol(symbol)
        if resolved is None:
            return None
        tick = mt5.symbol_info_tick(resolved)
        if tick is None:
            return None
        return (float(tick.bid) + float(tick.ask)) / 2.0

    def _prepare_symbol(self, symbol: str) -> Optional[str]:
        """מכניס את הסימול ל-Market Watch ומחכה לטיק. אם השם לא קיים, מחפש חלופה של זהב."""
        for candidate in self._symbol_candidates(symbol):
            for _ in range(4):
                mt5.symbol_select(candidate, True)
                info = mt5.symbol_info(candidate)
                tick = mt5.symbol_info_tick(candidate)
                if info is not None and tick is not None and float(tick.ask or 0) > 0:
                    if candidate != symbol:
                        _LOG.warning("Using broker symbol %s instead of %s", candidate, symbol)
                    return candidate
                time.sleep(0.15)
        return None

    def _symbol_candidates(self, symbol: str) -> list[str]:
        names = [symbol]
        stem = symbol.split(".")[0].upper()
        extras = []
        if stem == "XAUUSD":
            extras = ["XAUUSD.s", "XAUUSD.m", "XAUUSD", "GOLD"]
        elif stem.startswith("XAU") or stem == "GOLD":
            extras = [stem]
        for row in mt5.symbols_get() or []:
            name = row.name
            if name.upper() == stem or name.upper().startswith(stem + "."):
                extras.append(name)
        for name in extras:
            if name not in names:
                names.append(name)
        return names


def _normalize_price(price: float, info) -> float:
    tick = float(getattr(info, "trade_tick_size", 0) or getattr(info, "point", 0.01) or 0.01)
    digits = int(getattr(info, "digits", 2) or 2)
    steps = round(price / tick)
    return round(steps * tick, digits)


def _filling_candidates(info) -> list[int]:
    mode = int(getattr(info, "filling_mode", 0) or 0)
    ordered = []
    if mt5 is None:
        return []
    mapping = (
        (2, mt5.ORDER_FILLING_IOC),
        (1, mt5.ORDER_FILLING_FOK),
        (4, mt5.ORDER_FILLING_RETURN),
    )
    for flag, filling in mapping:
        if mode & flag:
            ordered.append(filling)
    for filling in (mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN):
        if filling not in ordered:
            ordered.append(filling)
    return ordered


def _discover_terminals() -> list[str]:
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
            for exe in root.rglob("terminal64.exe"):
                found.append(str(exe))
        except OSError:
            continue
    preferred = [p for p in found if "just" in p.lower() or "market" in p.lower()]
    others = [p for p in found if p not in preferred]
    return preferred + others
