from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional

from .brokers.base import Broker
from .config import AppConfig
from .db import Database
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

    def start(self) -> None:
        self.broker.connect()
        self._restore()
        self._thread = threading.Thread(target=self._run, name="trading", daemon=True)
        self._report_thread = threading.Thread(target=self._report_loop, name="excel", daemon=True)
        self._thread.start()
        self._report_thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.broker.shutdown()

    def submit(self, incoming: IncomingSignal) -> None:
        self._q.put(incoming)

    def _restore(self) -> None:
        open_trades = self.db.open_trades()
        for trade in open_trades:
            self._safety_due.setdefault(trade.signal_id, time.monotonic() + 1)
            if trade.sl_moved_to_be:
                self._be_done.add(trade.signal_id)
        if open_trades:
            _LOG.info("Restored %s open trades", len(open_trades))

    def _run(self) -> None:
        last_sched = 0.0
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

        active = self.db.active_signals()
        if len(active) >= self.cfg.max_concurrent_signals:
            rec = _new_signal(signal_id, item, symbol, SignalStatus.SKIPPED.value, "busy_one_signal")
            self.db.insert_signal(rec)
            self._queue_report(item.group.name, received)
            _LOG.warning("Skipped signal %s — another signal is active", signal_id)
            self.alert(f"דולג איתות מ-{item.group.name}: כבר יש איתות פתוח.", None)
            return

        rec = _new_signal(signal_id, item, symbol, SignalStatus.ACTIVE.value, "")
        self.db.insert_signal(rec)

        # --- EXECUTE FIRST, persist after each fill ---
        any_ok = False
        for index, tp_price in enumerate(item.parsed.tps, start=1):
            comment = f"GS|{item.group.name[:6]}|T{index}"[:31]
            result = None
            attempts = self.cfg.order_retries + 1
            for _ in range(attempts):
                result = self.broker.market_order(
                    symbol=symbol,
                    side=item.parsed.side,
                    volume=item.group.lot,
                    sl=item.parsed.sl,
                    tp=tp_price,
                    comment=comment,
                    deviation=self.cfg.deviation,
                    magic=self.cfg.magic_number,
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
                    lot=item.group.lot,
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
                    lot=item.group.lot,
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
                )
                self.db.insert_trade(failed)

        if not any_ok:
            self.db.update_signal_status(signal_id, SignalStatus.FAILED.value, skipped_reason="all_orders_failed")
            self.alert(f"כל הפקודות נכשלו לאיתות {signal_id}", None)
        else:
            self._safety_due[signal_id] = time.monotonic() + self.cfg.safety_delay_seconds
            _LOG.info("Executed signal %s with %s TPs", signal_id, len(item.parsed.tps))

        self._queue_report(item.group.name, received)

    def _monitor(self) -> None:
        open_trades = self.db.open_trades()
        if not open_trades:
            return
        live = {p.ticket: p for p in self.broker.positions(self.cfg.magic_number)}
        live_tickets = set(live)

        for trade in open_trades:
            if trade.ticket is None:
                continue
            if trade.ticket in live_tickets:
                continue
            deal = self.broker.closed_deal(trade.ticket)
            if deal is None:
                continue
            reason = deal.reason.value
            if trade.sl_moved_to_be and deal.reason in {CloseReason.SL, CloseReason.UNKNOWN}:
                if trade.entry_price is not None and abs(deal.exit_price - trade.entry_price) <= self.cfg.pip_size:
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
                trade.tp_index == self.cfg.breakeven_after_tp
                and reason == CloseReason.TP.value
            ):
                self._move_stops_to_entry(trade.signal_id)

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
            tp3 = next((t for t in group if t.tp_index == self.cfg.breakeven_after_tp), None)
            if tp3 is None:
                # still check closed TP3 via DB
                all_trades = self.db.trades_for_signal(signal_id)
                closed_tp3 = next(
                    (
                        t
                        for t in all_trades
                        if t.tp_index == self.cfg.breakeven_after_tp
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
        live = {p.ticket: p for p in self.broker.positions(self.cfg.magic_number)}
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
        for group in self.cfg.groups:
            path = self.write_month_file(group.name, year, month, final=True)
            self.alert(
                f"דוח חודשי {year:04d}-{month:02d} לקבוצה {group.name}",
                path,
            )
        self.db.set_meta(key, iso_now())
        _LOG.info("Monthly reports sent for %s-%s", year, month)

    def _maybe_daily(self, now: datetime) -> None:
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
            if path:
                self.alert(f"קובץ אקסל שוטף — {group.name}", path)
        self.alert("\n".join(lines), None)
        self.db.set_meta(key, iso_now())


def iso_now() -> str:
    return utcnow().isoformat()


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
    )
