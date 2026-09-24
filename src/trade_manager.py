from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from .brokers.base import Broker
from .config import AppConfig, load_config
from .db import Database
from .emailer import EmailSender
from .excel_report import ExcelReporter, month_bounds
from .models import (
    CloseReason,
    GroupConfig,
    ParsedSignal,
    SignalRecord,
    SignalStatus,
    TradeRecord,
    TradeStatus,
)
from .stats import max_tp_hit
from .timeutil import pips_from_prices, safety_levels, utcnow

_LOG = logging.getLogger(__name__)

AlertFn = Callable[[str, Optional[str]], None]


@dataclass
class IncomingSignal:
    parsed: ParsedSignal
    group: GroupConfig
    chat_id: int
    telegram_msg_id: int
    received_at: datetime
    raw_text: str


class TradingEngine:
    def __init__(
        self,
        cfg: AppConfig,
        db: Database,
        broker: Broker,
        reporter: ExcelReporter,
        alert: Optional[AlertFn] = None,
    ):
        self.cfg = cfg
        self.db = db
        self.broker = broker
        self.reporter = reporter
        self.alert = alert or (lambda *_: None)
        self._q: queue.Queue[IncomingSignal] = queue.Queue()
        self._report_q: queue.Queue[tuple[str, datetime]] = queue.Queue()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._report_thread: Optional[threading.Thread] = None
        self._safety_due: dict[str, float] = {}
        self._be_done: set[str] = set()
        self._guarded: set[int] = set()
        self._cfg_mtime: Optional[float] = None
        self._symbol_ok: Optional[bool] = None
        self.mailer = EmailSender(cfg.email)

    def start(self) -> None:
        # טלגרם חייב לעלות גם אם MT5 עדיין לא מאושר. כשיגיע איתות
        # ננסה להתחבר שוב ונפתח פוזיציה רק אם החשבון חי.
        try:
            self.broker.connect()
            self._check_symbol()
            self._recover()
        except Exception:
            _LOG.exception("Broker not ready at startup — Telegram listener will still start")
            self.alert(
                "הבוט מאזין לטלגרם, אבל MT5 לא מחובר. "
                "כשיגיע איתות ייעשה ניסיון נוסף לפתוח פוזיציה. "
                "ב-MT5: File > Login to Trade Account עד ש-Journal כותב authorized.",
                None,
            )
        self._thread = threading.Thread(target=self._run, name="trading", daemon=True)
        self._report_thread = threading.Thread(target=self._report_loop, name="excel", daemon=True)
        self._thread.start()
        self._report_thread.start()

    def _ensure_broker(self) -> bool:
        """מתחבר ל-MT5 אם עדיין לא מחוברים. dry_run/file_bridge תמיד מצליחים."""
        if getattr(self.broker, "_connected", None) is True:
            return True
        try:
            self.broker.connect()
        except Exception:
            _LOG.exception("Broker connect failed")
            return False
        if getattr(self.broker, "_connected", None) is False:
            return False
        return True

    def stop(self) -> None:
        self._stop.set()
        self.broker.shutdown()

    def submit(self, incoming: IncomingSignal) -> None:
        self._q.put(incoming)

    def _recover(self) -> None:
        """התאוששות אחרי קריסה או ריסטארט: מיישר את ה-DB מול המצב אצל הברוקר.

        שלושה מקרים: עסקאות שנסגרו בזמן שהבוט היה למטה, פוזיציות חיות שכבר
        מוכרות, ופוזיציות חיות שלא הספיקו להיכתב ל-DB לפני הקריסה.
        """
        open_trades = self.db.open_trades()
        known: set[int] = set()
        for trade in open_trades:
            self._safety_due.setdefault(trade.signal_id, time.monotonic() + 1)
            if trade.sl_moved_to_be:
                self._be_done.add(trade.signal_id)
            if trade.ticket is not None:
                known.add(int(trade.ticket))

        try:
            live_by_magic = self._positions_by_magic()
        except Exception:
            _LOG.exception("recovery: broker positions unavailable, keeping DB state as-is")
            return

        live_tickets = {pos.ticket for positions in live_by_magic.values() for pos in positions}

        closed = 0
        for trade in open_trades:
            if trade.ticket is None or int(trade.ticket) in live_tickets:
                continue
            if self._finalize_closed(trade):
                closed += 1

        adopted = 0
        for magic, positions in live_by_magic.items():
            for pos in positions:
                if int(pos.ticket) in known:
                    continue
                known.add(int(pos.ticket))
                if self.db.trade_by_ticket(pos.ticket) is not None:
                    continue
                if self._adopt_position(pos, magic):
                    adopted += 1

        _LOG.info(
            "Recovery: %s open in DB, %s closed while down, %s orphan positions adopted",
            len(open_trades),
            closed,
            adopted,
        )
        if closed or adopted:
            self.alert(
                f"התאוששות אחרי הפעלה מחדש: {closed} עסקאות נסגרו בזמן שהבוט היה למטה, "
                f"{adopted} פוזיציות אומצו.",
                None,
            )

    def _adopt_position(self, pos, magic: int) -> bool:
        """מאמץ פוזיציה חיה שאינה ב-DB כדי שתנוהל ותתועד כרגיל."""
        group_name, tp_index = _parse_trade_comment(pos.comment)
        if group_name is None:
            group = self._group_for_magic(magic)
            group_name = group.name if group else "recovered"
        signal = next(
            (s for s in self.db.active_signals() if s.group_name == group_name), None
        )
        signal_id = signal.id if signal else f"recovered-{pos.ticket}"
        now = utcnow()
        trade = TradeRecord(
            id=None,
            ticket=int(pos.ticket),
            signal_id=signal_id,
            group_name=group_name,
            tp_index=tp_index or 0,
            tp_price=float(pos.tp or 0.0),
            lot=float(pos.volume),
            side=pos.side.value,
            symbol=pos.symbol,
            received_at=signal.received_at if signal else now,
            entry_time=now,
            entry_price=float(pos.price_open),
            sl=float(pos.sl or 0.0),
            original_sl=float(pos.sl or 0.0),
            sl_moved_to_be=False,
            exit_time=None,
            exit_price=None,
            close_reason=None,
            profit=None,
            pips=None,
            status=TradeStatus.OPEN.value,
            zone_low=signal.zone_low if signal else 0.0,
            zone_high=signal.zone_high if signal else 0.0,
            telegram_chat_id=signal.chat_id if signal else 0,
            telegram_username=signal.username if signal else "",
        )
        self.db.insert_trade(trade)
        self._safety_due.setdefault(signal_id, time.monotonic() + 1)
        _LOG.warning(
            "Adopted orphan position ticket=%s group=%s tp_index=%s",
            pos.ticket,
            group_name,
            tp_index,
        )
        self._queue_report(group_name, trade.received_at)
        return True

    def _finalize_closed(self, trade: TradeRecord) -> bool:
        """סוגר רשומה ב-DB לפי העסקה בפועל אצל הברוקר."""
        deal = self.broker.closed_deal(trade.ticket)
        if deal is None:
            return False
        reason = deal.reason.value
        if trade.sl_moved_to_be and deal.reason in {CloseReason.SL, CloseReason.UNKNOWN}:
            if (
                trade.entry_price is not None
                and abs(deal.exit_price - trade.entry_price) <= self.cfg.pip_size
            ):
                reason = CloseReason.BREAKEVEN.value
        trade.exit_time = deal.exit_time
        trade.exit_price = deal.exit_price
        trade.profit = deal.profit
        trade.close_reason = reason
        trade.status = TradeStatus.CLOSED.value
        if trade.entry_price is not None:
            trade.pips = pips_from_prices(
                trade.side, trade.entry_price, deal.exit_price, self.cfg.pip_size
            )
        self.db.update_trade(trade)
        _LOG.info("Closed ticket %s reason=%s profit=%s", trade.ticket, reason, deal.profit)
        self._queue_report(trade.group_name, trade.received_at)
        if (
            trade.tp_index == self._breakeven_after_tp(trade.group_name)
            and reason == CloseReason.TP.value
        ):
            self._move_stops_to_entry(trade.signal_id)
        return True

    def _run(self) -> None:
        last_sched = 0.0
        last_guard = 0.0
        while not self._stop.is_set():
            try:
                item = self._q.get(timeout=0.2)
            except queue.Empty:
                item = None
            if item is not None:
                try:
                    self._handle(item)
                except Exception:
                    _LOG.exception("signal handling failed")
                    self.alert("שגיאה בטיפול באיתות. ראה לוג.", None)
            try:
                self._monitor()
                self._maybe_safety()
            except Exception:
                _LOG.exception("monitor failed")
            now = time.monotonic()
            if now - last_guard >= self.cfg.guard_interval_seconds:
                last_guard = now
                try:
                    self._guard_positions()
                except Exception:
                    _LOG.exception("guard failed")
                try:
                    self._maybe_reload_settings()
                except Exception:
                    _LOG.exception("config reload failed")
                try:
                    self._check_symbol()
                except Exception:
                    _LOG.exception("symbol check failed")
            if now - last_sched >= 20:
                last_sched = now
                try:
                    self._scheduler_tick()
                except Exception:
                    _LOG.exception("scheduler failed")

    def _handle(self, item: IncomingSignal) -> None:
        if self.db.already_processed(item.chat_id, item.telegram_msg_id):
            _LOG.info("Duplicate telegram message ignored %s/%s", item.chat_id, item.telegram_msg_id)
            return

        signal_id = _signal_id(item)
        symbol = self.cfg.symbol_override or item.parsed.symbol
        received = item.received_at

        if not self.cfg.trading_enabled or not item.group.enabled:
            reason = "trading_disabled" if not self.cfg.trading_enabled else "group_disabled"
            rec = _new_signal(signal_id, item, symbol, SignalStatus.SKIPPED.value, reason)
            self.db.insert_signal(rec)
            self._queue_report(item.group.name, received)
            _LOG.warning("Signal %s recorded but not executed (%s)", signal_id, reason)
            return

        active = self.db.active_signals()
        if len(active) >= self.cfg.max_concurrent_signals:
            rec = _new_signal(signal_id, item, symbol, SignalStatus.SKIPPED.value, "busy_one_signal")
            self.db.insert_signal(rec)
            self._queue_report(item.group.name, received)
            _LOG.warning("Skipped signal %s — another signal is active", signal_id)
            self.alert(f"דולג איתות מ-{item.group.name}: כבר יש איתות פתוח.", None)
            return

        # שורות ה-TP הראשונות מדולגות לחלוטין. המספור נשאר לפי השורה במקור,
        # כך ש-breakeven_after_tp=3 ממשיך להתייחס לשורה השלישית בהודעה.
        skip_first = self._skip_first_tps(item.group)
        tradable = [
            (index, price)
            for index, price in enumerate(item.parsed.tps, start=1)
            if index > skip_first
        ]
        if not tradable:
            rec = _new_signal(signal_id, item, symbol, SignalStatus.SKIPPED.value, "no_tp_after_skip")
            self.db.insert_signal(rec)
            self._queue_report(item.group.name, received)
            _LOG.warning(
                "Signal %s has %s TP lines, all within the skipped first %s",
                signal_id,
                len(item.parsed.tps),
                skip_first,
            )
            return

        if not self._ensure_broker():
            rec = _new_signal(signal_id, item, symbol, SignalStatus.FAILED.value, "mt5_not_connected")
            self.db.insert_signal(rec)
            self._queue_report(item.group.name, received)
            _LOG.error("Signal %s recorded but MT5 is not connected", signal_id)
            self.alert(
                f"איתות מ-{item.group.name} נקלט, אבל MT5 לא מחובר — לא נפתחה פוזיציה. "
                "File > Login to Trade Account עד ש-Journal כותב authorized.",
                None,
            )
            return

        rec = _new_signal(signal_id, item, symbol, SignalStatus.ACTIVE.value, "")
        self.db.insert_signal(rec)

        magic = item.group.magic or self.cfg.magic_number
        lot = self._order_lot(item.group)
        # --- EXECUTE FIRST, persist after each fill ---
        any_ok = False
        for index, tp_price in tradable:
            comment = f"GS|{item.group.name[:8]}|T{index}"[:31]
            result = None
            attempts = self.cfg.order_retries + 1
            for _ in range(attempts):
                result = self.broker.market_order(
                    symbol=symbol,
                    side=item.parsed.side,
                    volume=lot,
                    sl=item.parsed.sl,
                    tp=tp_price,
                    comment=comment,
                    deviation=self.cfg.deviation,
                    magic=magic,
                )
                if result.ok:
                    break
            if result and result.ok:
                any_ok = True
                trade = TradeRecord(
                    id=None,
                    ticket=result.ticket,
                    signal_id=signal_id,
                    group_name=item.group.name,
                    tp_index=index,
                    tp_price=tp_price,
                    # ה-EA יכול לדרוס את הלוט מהגרף, ולכן מתעדים את מה שבוצע.
                    lot=result.filled_volume or lot,
                    side=item.parsed.side.value,
                    symbol=symbol,
                    received_at=received,
                    entry_time=result.fill_time,
                    entry_price=result.fill_price,
                    sl=result.sl if result.sl is not None else item.parsed.sl,
                    original_sl=item.parsed.sl,
                    sl_moved_to_be=False,
                    exit_time=None,
                    exit_price=None,
                    close_reason=None,
                    profit=None,
                    pips=None,
                    status=TradeStatus.OPEN.value,
                    zone_low=item.parsed.zone_low,
                    zone_high=item.parsed.zone_high,
                    telegram_chat_id=item.chat_id,
                    telegram_username=item.group.username,
                )
                self.db.insert_trade(trade)
            else:
                msg = result.message if result else "no result"
                _LOG.error("Order failed TP%s: %s", index, msg)
                failed = TradeRecord(
                    id=None,
                    ticket=None,
                    signal_id=signal_id,
                    group_name=item.group.name,
                    tp_index=index,
                    tp_price=tp_price,
                    lot=lot,
                    side=item.parsed.side.value,
                    symbol=symbol,
                    received_at=received,
                    entry_time=None,
                    entry_price=None,
                    sl=item.parsed.sl,
                    original_sl=item.parsed.sl,
                    sl_moved_to_be=False,
                    exit_time=None,
                    exit_price=None,
                    close_reason=None,
                    profit=None,
                    pips=None,
                    status=TradeStatus.FAILED.value,
                    zone_low=item.parsed.zone_low,
                    zone_high=item.parsed.zone_high,
                    telegram_chat_id=item.chat_id,
                    telegram_username=item.group.username,
                )
                self.db.insert_trade(failed)

        if not any_ok:
            self.db.update_signal_status(signal_id, SignalStatus.FAILED.value, skipped_reason="all_orders_failed")
            last_msg = result.message if result else "no result"
            self.alert(f"כל הפקודות נכשלו לאיתות {signal_id}: {last_msg}", None)
        else:
            self._safety_due[signal_id] = time.monotonic() + self.cfg.safety_delay_seconds
            _LOG.info(
                "Executed signal %s: %s positions (TP%s..TP%s), skipped first %s of %s lines",
                signal_id,
                len(tradable),
                tradable[0][0],
                tradable[-1][0],
                skip_first,
                len(item.parsed.tps),
            )

        self._queue_report(item.group.name, received)

    def _magics(self) -> set[int]:
        magics = {self.cfg.magic_number}
        for group in self.cfg.groups:
            magics.add(group.magic or self.cfg.magic_number)
        return magics

    def _group_by_name(self, name: str) -> Optional[GroupConfig]:
        return next((g for g in self.cfg.groups if g.name == name), None)

    def _order_lot(self, group: GroupConfig) -> float:
        override = _read_chart_lot(self.cfg.common_files_dir)
        if override is None:
            return group.lot
        if override != group.lot:
            _LOG.info("Using chart lot %s instead of config %s", override, group.lot)
        return override

    def _skip_first_tps(self, group: Optional[GroupConfig]) -> int:
        if group is not None and group.skip_first_tps is not None:
            return group.skip_first_tps
        return self.cfg.skip_first_tps

    def _breakeven_after_tp(self, group_name: str) -> int:
        group = self._group_by_name(group_name)
        if group is not None and group.breakeven_after_tp is not None:
            return group.breakeven_after_tp
        return self.cfg.breakeven_after_tp

    def _group_for_magic(self, magic: int) -> Optional[GroupConfig]:
        for group in self.cfg.groups:
            if (group.magic or self.cfg.magic_number) == magic:
                return group
        return None

    def _positions_by_magic(self) -> dict[int, list]:
        return {magic: list(self.broker.positions(magic)) for magic in self._magics()}

    def _live_positions(self) -> dict:
        live = {}
        for positions in self._positions_by_magic().values():
            for pos in positions:
                live[pos.ticket] = pos
        return live

    def _monitor(self) -> None:
        open_trades = self.db.open_trades()
        if not open_trades:
            return
        live = self._live_positions()
        live_tickets = set(live)

        for trade in open_trades:
            if trade.ticket is None or trade.ticket in live_tickets:
                continue
            self._finalize_closed(trade)

        self._maybe_breakeven_by_price(open_trades)
        self._complete_if_done(open_trades)

    def _maybe_breakeven_by_price(self, open_trades: list[TradeRecord]) -> None:
        by_signal: dict[str, list[TradeRecord]] = {}
        for trade in open_trades:
            if trade.status != TradeStatus.OPEN.value:
                continue
            by_signal.setdefault(trade.signal_id, []).append(trade)
        for signal_id, group in by_signal.items():
            if signal_id in self._be_done:
                continue
            trigger = self._breakeven_after_tp(group[0].group_name)
            tp3 = next((t for t in group if t.tp_index == trigger), None)
            if tp3 is None:
                # still check the closed trigger leg via DB
                all_trades = self.db.trades_for_signal(signal_id)
                closed_tp3 = next(
                    (
                        t
                        for t in all_trades
                        if t.tp_index == trigger
                        and t.close_reason == CloseReason.TP.value
                    ),
                    None,
                )
                if closed_tp3:
                    self._move_stops_to_entry(signal_id)
                continue
            price = self.broker.last_price(tp3.symbol)
            if price is None:
                continue
            touched = (
                price >= tp3.tp_price
                if tp3.side == "BUY"
                else price <= tp3.tp_price
            )
            if touched:
                self._move_stops_to_entry(signal_id)

    def _move_stops_to_entry(self, signal_id: str) -> None:
        if signal_id in self._be_done:
            return
        trades = [t for t in self.db.trades_for_signal(signal_id) if t.status == TradeStatus.OPEN.value]
        moved = 0
        for trade in trades:
            if trade.ticket is None or trade.entry_price is None:
                continue
            ok = self.broker.modify_sl_tp(trade.ticket, sl=trade.entry_price, tp=trade.tp_price)
            if ok:
                self.db.mark_breakeven(trade.id, trade.entry_price)
                moved += 1
            else:
                _LOG.warning("Failed to move SL to entry ticket=%s", trade.ticket)
        self._be_done.add(signal_id)
        _LOG.info("Moved %s stops to entry for %s", moved, signal_id)
        if trades:
            self._queue_report(trades[0].group_name, trades[0].received_at)

    def _complete_if_done(self, snapshot: list[TradeRecord]) -> None:
        signal_ids = {t.signal_id for t in snapshot}
        for sid in set(t.signal_id for t in self.db.open_trades()) | signal_ids:
            trades = self.db.trades_for_signal(sid)
            if not trades:
                continue
            if any(t.status == TradeStatus.OPEN.value for t in trades):
                continue
            signal = self.db.get_signal(sid)
            if signal is None or signal.status != SignalStatus.ACTIVE.value:
                continue
            level = max_tp_hit(trades)
            self.db.update_signal_status(
                sid,
                SignalStatus.COMPLETED.value,
                max_tp_hit=level,
                completed_at=utcnow(),
            )
            self._safety_due.pop(sid, None)
            _LOG.info("Signal %s completed max_tp=%s", sid, level)
            self._queue_report(signal.group_name, signal.received_at)

    def _maybe_safety(self) -> None:
        due = [(sid, ts) for sid, ts in self._safety_due.items() if time.monotonic() >= ts]
        for signal_id, _ in due:
            self._apply_safety(signal_id)
            self._safety_due.pop(signal_id, None)

    def _apply_safety(self, signal_id: str) -> None:
        live = self._live_positions()
        trades = [t for t in self.db.trades_for_signal(signal_id) if t.status == TradeStatus.OPEN.value]
        for trade in trades:
            if trade.ticket is None or trade.ticket not in live:
                continue
            pos = live[trade.ticket]
            missing_sl = pos.sl is None or pos.sl == 0
            missing_tp = pos.tp is None or pos.tp == 0
            if not missing_sl and not missing_tp:
                continue
            if trade.entry_price is None:
                continue
            sl_s, tp_s = safety_levels(
                trade.side, trade.entry_price, self.cfg.safety_pips, self.cfg.pip_size
            )
            new_sl = sl_s if missing_sl else pos.sl
            new_tp = tp_s if missing_tp else pos.tp
            ok = self.broker.modify_sl_tp(trade.ticket, sl=new_sl, tp=new_tp)
            if ok:
                trade.sl = new_sl
                trade.tp_price = new_tp if missing_tp else trade.tp_price
                self.db.update_trade(trade)
                _LOG.warning("Safety SL/TP applied ticket=%s sl=%s tp=%s", trade.ticket, new_sl, new_tp)
                self.alert(f"מנגנון בטיחות הופעל על טיקט {trade.ticket}", None)
            else:
                _LOG.error("Safety modify failed ticket=%s", trade.ticket)

    def _check_symbol(self) -> None:
        """הסימול תלוי בחשבון שמחובר בטרמינל, והוא עלול להתחלף תוך כדי ריצה.

        מתריע רק כשהמצב משתנה, כדי לא להציף.
        """
        symbol = self.cfg.symbol_override
        if not symbol:
            return
        ok = self.broker.last_price(symbol) is not None
        if ok == self._symbol_ok:
            return
        self._symbol_ok = ok
        if ok:
            _LOG.info("Symbol %s is available again", symbol)
            self.alert(f"הסימול {symbol} חזר להיות זמין. המסחר יכול להימשך.", None)
        else:
            _LOG.error("Symbol %s is NOT available — orders will fail", symbol)
            self.alert(
                f"הסימול {symbol} לא זמין בחשבון שמחובר ב-MT5. כל פקודה תיכשל.\n"
                f"בדוק לאיזה חשבון הטרמינל מחובר, או עדכן symbol_override ב-config.yaml.",
                None,
            )

    def _maybe_reload_settings(self) -> None:
        """טעינה חמה של הידיות הידניות מ-config.yaml, בלי להפעיל מחדש.

        נטענים מחדש רק גודל הלוט, פרמטרי האסטרטגיה לכל קבוצה, והמתג הראשי.
        שאר ההגדרות דורשות הפעלה מחדש בכוונה, כדי לא לשבור ריצה פעילה.
        """
        path = self.cfg.config_path
        if path is None:
            return
        try:
            mtime = Path(path).stat().st_mtime
        except OSError:
            return
        if self._cfg_mtime is None:
            self._cfg_mtime = mtime
            return
        if mtime == self._cfg_mtime:
            return
        self._cfg_mtime = mtime

        try:
            fresh = load_config(Path(path))
        except Exception:
            _LOG.exception("config.yaml שונה אבל לא ניתן לטעינה — ממשיך עם הקודם")
            self.alert("config.yaml שונה אבל יש בו שגיאה. הבוט ממשיך עם ההגדרות הישנות.", None)
            return

        changes: list[str] = []
        by_name = {g.name: g for g in fresh.groups}
        for group in self.cfg.groups:
            new = by_name.get(group.name)
            if new is None:
                continue
            for attr, label in (
                ("lot", "לוט"),
                ("skip_first_tps", "דילוג TP"),
                ("breakeven_after_tp", "קידום אחרי TP"),
                ("enabled", "פעילה"),
            ):
                old_value = getattr(group, attr)
                new_value = getattr(new, attr)
                if old_value != new_value:
                    setattr(group, attr, new_value)
                    changes.append(f"{group.name}: {label} {old_value} -> {new_value}")

        if fresh.trading_enabled != self.cfg.trading_enabled:
            self.cfg.trading_enabled = fresh.trading_enabled
            state = "פעיל" if fresh.trading_enabled else "מושבת (מאזין ומתעד בלבד)"
            changes.append(f"מסחר: {state}")

        if changes:
            _LOG.info("Config reloaded: %s", "; ".join(changes))
            self.alert("עודכנו הגדרות:\n" + "\n".join(changes), None)

    def _guard_positions(self) -> None:
        """שומר בלתי תלוי באסטרטגיה: אף פוזיציה חיה לא נשארת בלי SL ו-TP.

        רץ על כל פוזיציה שנושאת magic שלנו, כולל כאלה שאינן ב-DB, ולא תלוי
        בשום לוגיקת איתות. זו רשת הביטחון האחרונה.
        """
        for pos in self._live_positions().values():
            missing_sl = not pos.sl
            missing_tp = not pos.tp
            if not missing_sl and not missing_tp:
                self._guarded.discard(int(pos.ticket))
                continue
            trade = self.db.trade_by_ticket(pos.ticket)
            fallback_sl, fallback_tp = safety_levels(
                pos.side.value, pos.price_open, self.cfg.safety_pips, self.cfg.pip_size
            )
            # מעדיפים את הרמות המקוריות של האיתות, ונופלים ל-50 פיפס רק אם אין.
            new_sl = pos.sl
            new_tp = pos.tp
            if missing_sl:
                new_sl = (trade.sl if trade and trade.sl else 0.0) or fallback_sl
            if missing_tp:
                new_tp = (trade.tp_price if trade and trade.tp_price else 0.0) or fallback_tp

            if not self.broker.modify_sl_tp(pos.ticket, sl=new_sl, tp=new_tp):
                _LOG.error("Guard failed to set SL/TP on ticket=%s", pos.ticket)
                continue
            _LOG.warning(
                "Guard set SL/TP ticket=%s sl=%s tp=%s (missing sl=%s tp=%s)",
                pos.ticket,
                new_sl,
                new_tp,
                missing_sl,
                missing_tp,
            )
            if trade is not None:
                trade.sl = new_sl
                if missing_tp:
                    trade.tp_price = new_tp
                self.db.update_trade(trade)
            if int(pos.ticket) not in self._guarded:
                self._guarded.add(int(pos.ticket))
                self.alert(f"מנגנון הגנה הוסיף SL/TP לפוזיציה {pos.ticket}", None)

    def _queue_report(self, group_name: str, when: datetime) -> None:
        self._report_q.put((group_name, when))

    def _report_loop(self) -> None:
        pending: dict[str, datetime] = {}
        while not self._stop.is_set():
            try:
                group, when = self._report_q.get(timeout=0.5)
                pending[group] = when
            except queue.Empty:
                pass
            if not pending:
                continue
            time.sleep(0.15)
            items = list(pending.items())
            pending.clear()
            for group, when in items:
                try:
                    self._write_excel(group, when, final=False)
                except Exception:
                    _LOG.exception("excel write failed for %s", group)

    def _write_excel(self, group_name: str, when: datetime, final: bool) -> Optional[str]:
        local = when.astimezone(self.cfg.tz)
        start, end = month_bounds(local.year, local.month, self.cfg.tz)
        signals = self.db.signals_in_range(group_name, start, end)
        trades = self.db.trades_in_range(group_name, start, end)
        path = self.reporter.write_month(
            group_name, local.year, local.month, signals, trades, final=final
        )
        return str(path)

    def write_month_file(self, group_name: str, year: int, month: int, final: bool) -> str:
        start, end = month_bounds(year, month, self.cfg.tz)
        signals = self.db.signals_in_range(group_name, start, end)
        trades = self.db.trades_in_range(group_name, start, end)
        path = self.reporter.write_month(group_name, year, month, signals, trades, final=final)
        return str(path)

    def _scheduler_tick(self) -> None:
        now = utcnow().astimezone(self.cfg.tz)
        self._maybe_monthly(now)
        self._maybe_daily(now)

    def _maybe_monthly(self, now: datetime) -> None:
        if now.month == 1:
            year, month = now.year - 1, 12
        else:
            year, month = now.year, now.month - 1
        key = f"monthly_sent_{year:04d}-{month:02d}"
        if self.db.get_meta(key):
            return
        start, end = month_bounds(year, month, self.cfg.tz)
        has_data = False
        for group in self.cfg.groups:
            if self.db.signals_in_range(group.name, start, end):
                has_data = True
                break
        if not has_data and now.day != 1:
            return
        paths = []
        for group in self.cfg.groups:
            path = self.write_month_file(group.name, year, month, final=True)
            paths.append(path)
            if self.cfg.monthly_telegram:
                self.alert(
                    f"דוח חודשי {year:04d}-{month:02d} לקבוצה {group.name}",
                    path,
                )
        emailed = self.send_monthly_email(year, month, paths)
        if not emailed and not self.cfg.monthly_telegram:
            # אין ערוץ יציאה פעיל — לפחות שיהיה עקבות בלוג ובטלגרם.
            _LOG.warning("Monthly report written to disk but not delivered anywhere")
            self.alert(
                f"דוח חודשי {year:04d}-{month:02d} נשמר בשרת, אבל שליחת המייל נכשלה.",
                None,
            )
        self.db.set_meta(key, iso_now())
        _LOG.info("Monthly reports sent for %s-%s", year, month)

    def send_monthly_email(self, year: int, month: int, paths: list[str]) -> bool:
        """מייל אחד לחודש עם קובץ אקסל לכל קבוצה, במקום הצפה בטלגרם."""
        if not self.cfg.email_monthly or not self.mailer.enabled:
            return False
        start, end = month_bounds(year, month, self.cfg.tz)
        lines = [f"דוח חודשי {year:04d}-{month:02d}", ""]
        for group in self.cfg.groups:
            signals = self.db.signals_in_range(group.name, start, end)
            trades = self.db.trades_in_range(group.name, start, end)
            closed = [t for t in trades if t.status == TradeStatus.CLOSED.value]
            profit = round(sum(t.profit or 0.0 for t in closed), 2)
            wins = len([t for t in closed if (t.profit or 0.0) > 0])
            lines.append(
                f"{group.name}: {len(signals)} איתותים, {len(trades)} עסקאות, "
                f"{len(closed)} סגורות, {wins} ברווח, סה\"כ {profit}"
            )
        lines += ["", "הפירוט המלא והסטטיסטיקה נמצאים בקבצים המצורפים."]
        return self.mailer.send(
            subject=f"דוח חודשי {year:04d}-{month:02d} — gold-signal-bot",
            body="\n".join(lines),
            attachments=[Path(p) for p in paths],
        )

    def _maybe_daily(self, now: datetime) -> None:
        if not self.cfg.daily_digest_enabled:
            return
        if now.hour != self.cfg.daily_digest_hour or now.minute < self.cfg.daily_digest_minute:
            return
        key = f"daily_sent_{now.strftime('%Y-%m-%d')}"
        if self.db.get_meta(key):
            return
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        lines = [f"סיכום יומי {now.strftime('%Y-%m-%d')}"]
        for group in self.cfg.groups:
            trades = self.db.trades_in_range(group.name, start, end)
            closed = [t for t in trades if t.status == "closed"]
            profit = round(sum(t.profit or 0.0 for t in closed), 2)
            lines.append(f"{group.name}: {len(trades)} עסקאות, {len(closed)} סגורות, P/L {profit}")
            path = self._write_excel(group.name, now, final=False)
            if path and self.cfg.daily_digest_files:
                self.alert(f"קובץ אקסל שוטף — {group.name}", path)
        self.alert("\n".join(lines), None)
        self.db.set_meta(key, iso_now())


def iso_now() -> str:
    return utcnow().isoformat()


def _read_chart_lot(common_files_dir: str) -> Optional[float]:
    """קורא את הלוט מחלון Inputs של GoldSignalBridge (gs_lot.txt)."""
    paths: list[Path] = []
    if common_files_dir:
        paths.append(Path(common_files_dir) / "gs_lot.txt")
    paths.append(Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal" / "Common" / "Files" / "gs_lot.txt")
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if not path.exists():
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[0]
            value = float(raw.split("|")[-1] if "|" in raw else raw)
        except (OSError, ValueError, IndexError):
            continue
        if value > 0:
            return value
    return None


def _parse_trade_comment(comment: str) -> tuple[Optional[str], Optional[int]]:
    """הערת העסקה נכתבת כ-GS|<group>|T<index> ומאפשרת לשחזר שיוך אחרי קריסה."""
    if not comment:
        return None, None
    parts = str(comment).split("|")
    if len(parts) < 3 or parts[0] != "GS":
        return None, None
    group = parts[1].strip() or None
    index = None
    token = parts[2].strip().upper()
    if token.startswith("T") and token[1:].isdigit():
        index = int(token[1:])
    return group, index


def _signal_id(item: IncomingSignal) -> str:
    ts = item.received_at.astimezone().strftime("%Y%m%d-%H%M%S")
    return f"{ts}-{abs(item.chat_id) % 1000000}-{item.telegram_msg_id}"


def _new_signal(
    signal_id: str, item: IncomingSignal, symbol: str, status: str, reason: str
) -> SignalRecord:
    return SignalRecord(
        id=signal_id,
        group_name=item.group.name,
        chat_id=item.chat_id,
        telegram_msg_id=item.telegram_msg_id,
        received_at=item.received_at,
        symbol=symbol,
        side=item.parsed.side.value,
        zone_low=item.parsed.zone_low,
        zone_high=item.parsed.zone_high,
        sl=item.parsed.sl,
        raw_text=item.raw_text,
        status=status,
        skipped_reason=reason,
        tps=item.parsed.tps,
        username=item.group.username,
    )
