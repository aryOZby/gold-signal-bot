from __future__ import annotations

import asyncio
import logging
from datetime import timezone
from pathlib import Path
from typing import Optional

from telethon import TelegramClient, events
from telethon.tl.custom.message import Message
from telethon.utils import get_peer_id

from .alerts import AlertBus
from .config import AppConfig, group_by_chat_id, group_by_username
from .models import GroupConfig
from .parser import parse_signal
from .timeutil import utcnow
from .trade_manager import IncomingSignal, TradingEngine

_LOG = logging.getLogger(__name__)


class TelegramService:
    def __init__(self, cfg: AppConfig, engine: TradingEngine, alerts: AlertBus):
        self.cfg = cfg
        self.engine = engine
        self.alerts = alerts
        session = Path(cfg.data_dir) / cfg.session_name
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        self.client = TelegramClient(str(session), cfg.telegram_api_id, cfg.telegram_api_hash)

    async def start(self) -> None:
        await self.client.start(phone=self.cfg.telegram_phone or None)
        me = await self.client.get_me()
        _LOG.info("Telegram signed in as %s id=%s", getattr(me, "username", None) or me.id, me.id)
        await self._resolve_usernames()
        self.client.add_event_handler(self._on_message, events.NewMessage())
        asyncio.create_task(self._drain_alerts())

    async def _resolve_usernames(self) -> None:
        for group in self.cfg.groups:
            if not group.username:
                continue
            try:
                entity = await self.client.get_entity(group.username)
                group.chat_id = int(get_peer_id(entity))
                title = getattr(entity, "title", None) or getattr(entity, "username", group.username)
                _LOG.info("Resolved @%s (%s) -> chat_id=%s", group.username, title, group.chat_id)
            except Exception:
                _LOG.exception(
                    "לא הצלחתי לפתור את @%s — ודא שהחשבון חבר/מנוי בקבוצה או בערוץ",
                    group.username,
                )

    async def run_until_disconnected(self) -> None:
        await self.client.run_until_disconnected()

    async def _on_message(self, event: events.NewMessage.Event) -> None:
        msg: Message = event.message
        chat_id = event.chat_id
        if chat_id is None:
            return
        text = msg.raw_text or ""
        group = group_by_chat_id(self.cfg, int(chat_id))
        if group is None:
            group = await self._match_by_username(event, int(chat_id))
        if group is None:
            if text.strip():
                _LOG.info("Ignored chat_id=%s (not in config). Preview: %s", chat_id, text[:80])
            return
        parsed = parse_signal(text)
        if parsed is None:
            return
        received = msg.date
        if received is None:
            received = utcnow()
        elif received.tzinfo is None:
            received = received.replace(tzinfo=timezone.utc)
        incoming = IncomingSignal(
            parsed=parsed,
            group=group,
            chat_id=int(chat_id),
            telegram_msg_id=int(msg.id),
            received_at=received,
            raw_text=text,
        )
        _LOG.info("Signal from %s: %s %s TPs=%s", group.name, parsed.side.value, parsed.symbol, parsed.tp_count)
        self.engine.submit(incoming)

    async def _match_by_username(self, event: events.NewMessage.Event, chat_id: int) -> Optional[GroupConfig]:
        chat = event.chat
        username = getattr(chat, "username", None) if chat is not None else None
        if not username:
            try:
                chat = await event.get_chat()
                username = getattr(chat, "username", None)
            except Exception:
                return None
        group = group_by_username(self.cfg, username)
        if group is not None and not group.chat_id:
            group.chat_id = chat_id
            _LOG.info("Bound @%s -> chat_id=%s", group.username, chat_id)
        return group

    async def _drain_alerts(self) -> None:
        while True:
            text, file_path = await asyncio.to_thread(self.alerts.q.get)
            try:
                await self._send_admin(text, file_path)
            except Exception:
                _LOG.exception("failed to send admin alert")

    async def _send_admin(self, text: str, file_path: Optional[str]) -> None:
        if not self.cfg.admin_chat_id:
            return
        if file_path:
            await self.client.send_file(self.cfg.admin_chat_id, file_path, caption=text or None)
        elif text:
            await self.client.send_message(self.cfg.admin_chat_id, text)


def describe_groups(groups: list[GroupConfig]) -> str:
    parts = []
    for g in groups:
        if g.username:
            parts.append(f"{g.name}=@{g.username}" + (f"({g.chat_id})" if g.chat_id else ""))
        else:
            parts.append(f"{g.name}={g.chat_id}")
    return ", ".join(parts)
