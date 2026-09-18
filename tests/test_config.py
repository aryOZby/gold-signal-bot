from src.config import chat_id_aliases, group_by_chat_id, AppConfig
from src.models import GroupConfig
from pathlib import Path
from zoneinfo import ZoneInfo


def test_web_k_id_matches_telethon_supergroup_id():
    web = -2001216034
    telethon = -1002001216034
    assert telethon in chat_id_aliases(web)
    assert web in chat_id_aliases(telethon)


def test_group_lookup_accepts_both_id_forms():
    cfg = AppConfig(
        timezone="Asia/Jerusalem",
        dry_run=True,
        session_name="t",
        groups=[GroupConfig("group_a", -2001216034, 0.01)],
        admin_chat_id=0,
        telegram_api_id=0,
        telegram_api_hash="",
        telegram_phone="",
        symbol_override="",
            max_concurrent_signals=1,
            skip_first_tps=2,
            breakeven_after_tp=3,
            safety_delay_seconds=5,
            safety_pips=50,
            guard_interval_seconds=5,
            pip_size=0.1,
        magic_number=1,
        deviation=10,
        order_retries=0,
        broker_type="dry_run",
        common_files_dir="",
        mt5_login=None,
        mt5_password="",
        mt5_server="",
        mt5_terminal_path="",
        output_dir=Path("."),
        daily_digest_hour=23,
        daily_digest_minute=55,
        data_dir=Path("."),
        logs_dir=Path("."),
        lot_size_default=0.01,
        tz=ZoneInfo("Asia/Jerusalem"),
    )
    assert group_by_chat_id(cfg, -2001216034) is not None
    assert group_by_chat_id(cfg, -1002001216034) is not None
    assert group_by_chat_id(cfg, -1) is None


def test_group_lookup_by_username():
    from src.config import group_by_username

    cfg = AppConfig(
        timezone="Asia/Jerusalem",
        dry_run=True,
        session_name="t",
        groups=[GroupConfig("TechnicalPips6273", 0, 0.01, username="TechnicalPips6273")],
        admin_chat_id=0,
        telegram_api_id=0,
        telegram_api_hash="",
        telegram_phone="",
        symbol_override="",
            max_concurrent_signals=1,
            skip_first_tps=2,
            breakeven_after_tp=3,
            safety_delay_seconds=5,
            safety_pips=50,
            guard_interval_seconds=5,
            pip_size=0.1,
        magic_number=1,
        deviation=10,
        order_retries=0,
        broker_type="dry_run",
        common_files_dir="",
        mt5_login=None,
        mt5_password="",
        mt5_server="",
        mt5_terminal_path="",
        output_dir=Path("."),
        daily_digest_hour=23,
        daily_digest_minute=55,
        data_dir=Path("."),
        logs_dir=Path("."),
        lot_size_default=0.01,
        tz=ZoneInfo("Asia/Jerusalem"),
    )
    assert group_by_username(cfg, "@TechnicalPips6273") is not None
    assert group_by_username(cfg, "technicalpips6273") is not None
    assert group_by_username(cfg, "other") is None
    assert group_by_chat_id(cfg, 0) is None


def test_isolate_group_drops_foreign_rows():
    from src.excel_report import isolate_group
    from src.models import SignalRecord, TradeRecord
    from src.timeutil import utcnow

    now = utcnow()
    signals = [
        SignalRecord("a", "group_a", 1, 1, now, "XAUUSD", "SELL", 1, 2, 3, "", "completed"),
        SignalRecord("b", "group_b", 2, 1, now, "XAUUSD", "BUY", 1, 2, 3, "", "completed"),
    ]
    trades = [
        TradeRecord(1, 1, "a", "group_a", 1, 1, 0.01, "SELL", "XAUUSD", now, now, 1, 1, 1, False, now, 1, "TP", 1, 1, "closed"),
        TradeRecord(2, 2, "b", "group_b", 1, 1, 0.01, "BUY", "XAUUSD", now, now, 1, 1, 1, False, now, 1, "TP", 1, 1, "closed"),
    ]
    sigs, trs = isolate_group("group_a", signals, trades)
    assert [s.id for s in sigs] == ["a"]
    assert [t.group_name for t in trs] == ["group_a"]
