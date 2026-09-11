from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from ..models import BrokerPosition, ClosedDeal, CloseReason, OrderResult, Side
from ..timeutil import utcnow
from .base import Broker

_LOG = logging.getLogger(__name__)


class FileBridgeBroker(Broker):
    """Talks to GoldSignalBridge.mq5 via MT5 Common/Files."""

    def __init__(self, common_files_dir: str, timeout: float = 5.0):
        if not common_files_dir:
            raise RuntimeError("broker.common_files_dir is required for file_bridge")
        self.root = Path(common_files_dir)
        self.timeout = timeout
        self._seen_closes: set[int] = set()

    def connect(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        heartbeat = self.root / "gs_heartbeat.txt"
        if not heartbeat.exists():
            _LOG.warning(
                "No gs_heartbeat.txt in %s — attach GoldSignalBridge.mq5 to an XAUUSD chart",
                self.root,
            )

    def shutdown(self) -> None:
        return

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
        uid = uuid4().hex
        line = "|".join(
            [
                "MARKET",
                uid,
                symbol,
                side.value,
                f"{volume:.4f}",
                f"{sl:.5f}",
                f"{tp:.5f}",
                str(deviation),
                str(magic),
                comment.replace("|", "/")[:31],
            ]
        )
        res = self._roundtrip(uid, line)
        if res is None:
            return OrderResult(False, None, None, None, message="bridge timeout")
        parts = res.strip().split("|")
        # RES|uid|OK|ticket|price|retcode
        if len(parts) < 4 or parts[2] != "OK":
            return OrderResult(
                False,
                None,
                None,
                None,
                message=res,
            )
        ticket = int(float(parts[3]))
        price = float(parts[4]) if len(parts) > 4 else 0.0
        retcode = int(float(parts[5])) if len(parts) > 5 else 0
        return OrderResult(
            ok=True,
            ticket=ticket,
            fill_price=price,
            fill_time=utcnow(),
            retcode=retcode,
            message="bridge",
            sl=sl,
            tp=tp,
        )

    def modify_sl_tp(self, ticket: int, sl: Optional[float], tp: Optional[float]) -> bool:
        uid = uuid4().hex
        sl_s = "" if sl is None else f"{sl:.5f}"
        tp_s = "" if tp is None else f"{tp:.5f}"
        line = f"MODIFY|{uid}|{ticket}|{sl_s}|{tp_s}"
        res = self._roundtrip(uid, line)
        return bool(res and "|OK|" in res)

    def positions(self, magic: int) -> list[BrokerPosition]:
        path = self.root / "gs_positions.txt"
        if not path.exists():
            return []
        out: list[BrokerPosition] = []
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        for line in text.splitlines():
            if not line.startswith("POS|"):
                continue
            parts = line.split("|")
            # POS|ticket|symbol|side|volume|open|sl|tp|profit|comment|magic
            if len(parts) < 10:
                continue
            try:
                if len(parts) > 10 and int(float(parts[10])) != magic:
                    continue
                out.append(
                    BrokerPosition(
                        ticket=int(float(parts[1])),
                        symbol=parts[2],
                        side=Side.BUY if parts[3].upper() == "BUY" else Side.SELL,
                        volume=float(parts[4]),
                        price_open=float(parts[5]),
                        sl=float(parts[6] or 0),
                        tp=float(parts[7] or 0),
                        profit=float(parts[8] or 0),
                        comment=parts[9],
                    )
                )
            except (TypeError, ValueError):
                continue
        return out

    def closed_deal(self, ticket: int) -> Optional[ClosedDeal]:
        path = self.root / "gs_closed.txt"
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        last = None
        for line in text.splitlines():
            if not line.startswith("CLOSE|"):
                continue
            parts = line.split("|")
            # CLOSE|ticket|price|unix|profit|REASON
            if len(parts) < 6:
                continue
            try:
                if int(float(parts[1])) != ticket:
                    continue
                ts = datetime.fromtimestamp(float(parts[3]), tz=timezone.utc)
                reason_raw = parts[5].upper()
                reason = {
                    "TP": CloseReason.TP,
                    "SL": CloseReason.SL,
                    "BE": CloseReason.BREAKEVEN,
                    "MANUAL": CloseReason.MANUAL,
                }.get(reason_raw, CloseReason.UNKNOWN)
                last = ClosedDeal(
                    ticket=ticket,
                    exit_price=float(parts[2]),
                    exit_time=ts,
                    profit=float(parts[4]),
                    reason=reason,
                )
            except (TypeError, ValueError):
                continue
        return last

    def last_price(self, symbol: str) -> Optional[float]:
        path = self.root / "gs_tick.txt"
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            # TICK|symbol|bid|ask
            parts = text.split("|")
            if len(parts) >= 4 and parts[1] == symbol:
                return (float(parts[2]) + float(parts[3])) / 2.0
        except (OSError, ValueError):
            return None
        return None

    def _roundtrip(self, uid: str, line: str) -> Optional[str]:
        cmd = self.root / f"gs_cmd_{uid}.txt"
        res = self.root / f"gs_res_{uid}.txt"
        tmp = self.root / f"gs_cmd_{uid}.tmp"
        tmp.write_text(line + "\n", encoding="utf-8")
        tmp.replace(cmd)
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            if res.exists():
                try:
                    payload = res.read_text(encoding="utf-8", errors="replace")
                    if payload.strip():
                        try:
                            res.unlink(missing_ok=True)
                        except OSError:
                            pass
                        return payload
                except OSError:
                    pass
            time.sleep(0.02)
        _LOG.error("file bridge timeout uid=%s", uid)
        return None
