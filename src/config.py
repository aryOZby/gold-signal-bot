from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv

from .emailer import EmailSettings, parse_recipients
from .models import GroupConfig


ROOT = Path(__file__).resolve().parent.parent


@dataclass
class AppConfig:
    timezone: str
    dry_run: bool
    session_name: str
    groups: list[GroupConfig]
    admin_chat_id: int
    telegram_api_id: int
    telegram_api_hash: str
    telegram_phone: str
    symbol_override: str
    max_concurrent_signals: int
    skip_first_tps: int
    breakeven_after_tp: int
    safety_delay_seconds: float
    safety_pips: float
    guard_interval_seconds: float
    pip_size: float
    magic_number: int
    deviation: int
    order_retries: int
    broker_type: str
    common_files_dir: str
    mt5_login: Optional[int]
    mt5_password: str
    mt5_server: str
    mt5_terminal_path: str
    output_dir: Path
    daily_digest_hour: int
    daily_digest_minute: int
    data_dir: Path
    logs_dir: Path
    lot_size_default: float
    tz: ZoneInfo
    # שדות חדשים נוספים כאן עם ברירת מחדל, כדי לא לשבור קריאות קיימות.
    email: EmailSettings = field(default_factory=EmailSettings)
    email_monthly: bool = True
    daily_digest_enabled: bool = True
    # הדוח החודשי הולך למייל. שלח גם לטלגרם רק אם מבקשים במפורש.
    monthly_telegram: bool = False
    # הסיכום היומי בטלגרם הוא טקסט בלבד, בלי לצרף קבצי אקסל.
    daily_digest_files: bool = False
    # מתג ראשי. false = ממשיך להאזין ולתעד, אבל לא פותח פוזיציות.
    trading_enabled: bool = True
    # נשמר כדי שנוכל לטעון מחדש לוט/אסטרטגיה בלי להפעיל מחדש את הבוט.
    config_path: Optional[Path] = None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_config(path: Optional[Path] = None) -> AppConfig:
    load_dotenv(ROOT / ".env")
    cfg_path = path or ROOT / "config.yaml"
    if not cfg_path.exists():
        example = ROOT / "config.example.yaml"
        if not example.exists():
            raise FileNotFoundError("Missing config.yaml and config.example.yaml")
        cfg_path = example

    with cfg_path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    telegram = raw.get("telegram") or {}
    trading = raw.get("trading") or {}
    broker = raw.get("broker") or {}
    excel = raw.get("excel") or {}
    paths = raw.get("paths") or {}

    groups = []
    default_lot = float(os.getenv("LOT_SIZE", "0.01"))
    default_magic = int(trading.get("magic_number") or 260908)
    for item in telegram.get("groups") or []:
        name = str(item["name"]).strip()
        env_id = os.getenv(f"TELEGRAM_{name.upper()}_CHAT_ID")
        env_user = os.getenv(f"TELEGRAM_{name.upper()}_USERNAME")
        username = str(env_user or item.get("username") or "").strip().lstrip("@")
        raw_id = env_id if env_id not in (None, "") else item.get("chat_id", 0)
        try:
            chat_id = int(raw_id or 0)
        except (TypeError, ValueError):
            token = str(raw_id).strip().lstrip("@")
            if token and not username:
                username = token
            chat_id = 0
        if not chat_id and not username:
            raise ValueError(f"Group {name} needs chat_id or username")
        magic = int(item.get("magic") or (default_magic + len(groups)))
        skip = item.get("skip_first_tps")
        be_after = item.get("breakeven_after_tp")
        groups.append(
            GroupConfig(
                name=name,
                chat_id=chat_id,
                lot=float(item.get("lot", default_lot)),
                username=username,
                magic=magic,
                skip_first_tps=None if skip is None else max(0, int(skip)),
                breakeven_after_tp=None if be_after is None else max(1, int(be_after)),
            )
        )
    if len(groups) < 1:
        raise ValueError("Configure at least one Telegram group in config.yaml")

    tz_name = str(raw.get("timezone") or "Asia/Jerusalem")
    dry_run = _env_bool("DRY_RUN", bool(raw.get("dry_run", True)))
    admin = os.getenv("TELEGRAM_ADMIN_CHAT_ID") or telegram.get("admin_chat_id") or 0

    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH") or ""
    phone = os.getenv("TELEGRAM_PHONE") or ""

    login = os.getenv("MT5_LOGIN")
    data_dir = ROOT / str(paths.get("data_dir") or "data")
    logs_dir = ROOT / str(paths.get("logs_dir") or "logs")
    output_dir = ROOT / str(excel.get("output_dir") or "reports")

    broker_type = str(broker.get("type") or "dry_run").strip().lower()
    if dry_run:
        broker_type = "dry_run"

    return AppConfig(
        timezone=tz_name,
        dry_run=dry_run,
        session_name=str(telegram.get("session_name") or "gold_signal_bot"),
        groups=groups,
        admin_chat_id=int(admin or 0),
        telegram_api_id=int(api_id) if api_id else 0,
        telegram_api_hash=api_hash,
        telegram_phone=phone,
        symbol_override=str(trading.get("symbol_override") or "").strip(),
        max_concurrent_signals=int(trading.get("max_concurrent_signals") or 1),
        skip_first_tps=max(0, int(trading.get("skip_first_tps", 2) or 0)),
        breakeven_after_tp=int(trading.get("breakeven_after_tp") or 3),
        safety_delay_seconds=float(trading.get("safety_delay_seconds") or 5),
        safety_pips=float(trading.get("safety_pips") or 50),
        guard_interval_seconds=float(trading.get("guard_interval_seconds") or 5),
        pip_size=float(trading.get("pip_size") or 0.1),
        magic_number=int(trading.get("magic_number") or 260908),
        deviation=int(trading.get("deviation") or 30),
        order_retries=int(trading.get("order_retries") or 1),
        broker_type=broker_type,
        common_files_dir=str(broker.get("common_files_dir") or "").strip(),
        mt5_login=int(login) if login else None,
        mt5_password=os.getenv("MT5_PASSWORD") or "",
        mt5_server=os.getenv("MT5_SERVER") or "",
        mt5_terminal_path=os.getenv("MT5_TERMINAL_PATH") or "",
        output_dir=output_dir,
        email=EmailSettings(
            host=os.getenv("SMTP_HOST") or "",
            port=int(os.getenv("SMTP_PORT") or 587),
            user=os.getenv("SMTP_USER") or "",
            password=os.getenv("SMTP_PASSWORD") or "",
            sender=os.getenv("EMAIL_FROM") or os.getenv("SMTP_USER") or "",
            recipients=parse_recipients(os.getenv("EMAIL_TO")),
        ),
        email_monthly=bool(excel.get("email_monthly", True)),
        daily_digest_enabled=bool(excel.get("daily_digest", True)),
        monthly_telegram=bool(excel.get("monthly_telegram", False)),
        daily_digest_files=bool(excel.get("daily_digest_files", False)),
        trading_enabled=bool(trading.get("enabled", True)),
        config_path=cfg_path,
        daily_digest_hour=int(excel.get("daily_digest_hour") or 23),
        daily_digest_minute=int(excel.get("daily_digest_minute") or 55),
        data_dir=data_dir,
        logs_dir=logs_dir,
        lot_size_default=default_lot,
        tz=ZoneInfo(tz_name),
    )


def chat_id_aliases(chat_id: int) -> set[int]:
    """web.telegram.org/k/#-2001216034 vs Telethon/Bot API -1002001216034."""
    ids = {int(chat_id)}
    raw = abs(int(chat_id))
    text = str(raw)
    if text.startswith("100") and len(text) > 9:
        ids.add(-int(text[3:]))
    else:
        ids.add(-int(f"100{raw}"))
    return ids


def group_by_chat_id(cfg: AppConfig, chat_id: int) -> Optional[GroupConfig]:
    if not chat_id:
        return None
    incoming = chat_id_aliases(chat_id)
    for group in cfg.groups:
        if not group.chat_id:
            continue
        if incoming & chat_id_aliases(group.chat_id):
            return group
    return None


def group_by_username(cfg: AppConfig, username: Optional[str]) -> Optional[GroupConfig]:
    if not username:
        return None
    key = str(username).strip().lstrip("@").lower()
    if not key:
        return None
    for group in cfg.groups:
        if group.username and group.username.strip().lstrip("@").lower() == key:
            return group
    return None
