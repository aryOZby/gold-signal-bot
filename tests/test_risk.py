from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.models import TradeRecord
from src.parser import parse_signal
from src.risk import (
    RiskSettings,
    daily_loss_reached,
    parse_risk_settings,
    risk_lot,
    validate_signal,
)
from test_engine import BUY, SELL, _engine, _incoming

WINDOW = (datetime(2020, 1, 1, tzinfo=timezone.utc), datetime(2030, 1, 1, tzinfo=timezone.utc))

BAD_SL_SELL = """#XAUUSD SELL 4315-4318

TP 4312
TP 4309
TP 4305

SL 4310
"""


# --- signal sanity checks -------------------------------------------------


def test_valid_signals_pass():
    assert validate_signal(parse_signal(SELL)) is None
    assert validate_signal(parse_signal(BUY)) is None


def test_sl_on_wrong_side_is_rejected():
    assert validate_signal(parse_signal(BAD_SL_SELL)) == "sl_wrong_side"
    buy = replace(parse_signal(BUY), sl=4350.0)
    assert validate_signal(buy) == "sl_wrong_side"


def test_tp_on_wrong_side_is_rejected():
    sell = replace(parse_signal(SELL), tps=(4312.0, 4320.0))
    assert validate_signal(sell) == "tp_wrong_side"
    buy = replace(parse_signal(BUY), tps=(4340.0,))
    assert validate_signal(buy) == "tp_wrong_side"


def test_market_already_past_sl_is_rejected():
    sell = parse_signal(SELL)
    assert validate_signal(sell, market_price=4328.0) == "sl_already_hit"
    assert validate_signal(sell, market_price=4316.0) is None
    buy = parse_signal(BUY)
    assert validate_signal(buy, market_price=4336.0) == "sl_already_hit"


def test_max_sl_distance():
    sell = parse_signal(SELL)  # zone mid 4316.5, SL 4327 -> 105 pips
    assert validate_signal(sell, max_sl_pips=100, pip_size=0.1) == "sl_too_far"
    assert validate_signal(sell, max_sl_pips=110, pip_size=0.1) is None
    assert validate_signal(sell, max_sl_pips=0, pip_size=0.1) is None


# --- risk-based lot sizing ------------------------------------------------


def _lot(**kw):
    args = dict(
        balance=10_000, risk_percent=1.0, entry=4316.5, sl=4327.0, legs=3,
        value_per_price_unit=100.0, min_lot=0.01, max_lot=1.0, lot_step=0.01,
    )
    args.update(kw)
    return risk_lot(**args)


def test_risk_lot_splits_budget_across_legs_and_rounds_down():
    # $100 budget / (10.5 price * $100 * 3 legs) = 0.0317 -> 0.03
    assert _lot() == 0.03
    assert _lot(legs=1) == 0.09


def test_risk_lot_caps_at_max_lot():
    assert _lot(balance=10_000_000, max_lot=0.5) == 0.5


def test_risk_lot_refuses_to_over_risk():
    assert _lot(balance=100) is None
    assert _lot(entry=4327.0) is None


# --- daily loss limit -----------------------------------------------------


def test_daily_loss_limit_money_and_percent():
    assert daily_loss_reached(-150, None, limit=100, limit_percent=0) is True
    assert daily_loss_reached(-50, None, limit=100, limit_percent=0) is False
    assert daily_loss_reached(50, None, limit=100, limit_percent=0) is False
    # start-of-day balance 10,000; 3% = 300
    assert daily_loss_reached(-300, 9_700, limit=0, limit_percent=3) is True
    assert daily_loss_reached(-299, 9_701, limit=0, limit_percent=3) is False
    assert daily_loss_reached(-10_000, None, limit=0, limit_percent=0) is False


# --- config ---------------------------------------------------------------


def test_risk_defaults_are_all_off():
    settings = parse_risk_settings(None)
    assert settings == RiskSettings()
    assert settings.lot_mode == "fixed"
    assert settings.sanity_checks is False
    assert settings.daily_loss_limit == 0 and settings.daily_loss_limit_percent == 0


def test_risk_section_loads_from_yaml(tmp_path: Path):
    from src.config import load_config

    path = tmp_path / "config.yaml"
    path.write_text(
        "telegram:\n  groups:\n    - name: a\n      chat_id: -1\n"
        "risk:\n  lot_mode: risk_percent\n  risk_percent: 0.5\n  max_lot: 0.2\n"
        "  sanity_checks: true\n  max_sl_pips: 150\n  daily_loss_limit: 200\n",
        encoding="utf-8",
    )
    risk = load_config(path).risk
    assert risk.uses_risk_percent
    assert (risk.risk_percent, risk.max_lot, risk.max_sl_pips, risk.daily_loss_limit) == (0.5, 0.2, 150, 200)
    assert risk.sanity_checks is True


def test_example_config_keeps_risk_controls_off():
    from src.config import ROOT, load_config

    cfg = load_config(ROOT / "config.example.yaml")
    assert cfg.risk == RiskSettings()


def test_invalid_risk_config_is_rejected():
    with pytest.raises(ValueError):
        parse_risk_settings({"lot_mode": "martingale"})
    with pytest.raises(ValueError):
        parse_risk_settings({"lot_mode": "risk_percent", "risk_percent": 50})


# --- engine integration ---------------------------------------------------


def test_default_engine_still_executes_without_checks(tmp_path: Path):
    engine, db, broker = _engine(tmp_path)
    engine._handle(_incoming(BAD_SL_SELL, engine.cfg.groups[0], 1))
    assert len(broker.positions(engine.cfg.magic_number)) == 1


def test_engine_rejects_bad_signal_when_checks_enabled(tmp_path: Path):
    engine, db, broker = _engine(tmp_path)
    engine.cfg.risk = RiskSettings(sanity_checks=True)
    alerts: list[str] = []
    engine.alert = lambda text, path=None: alerts.append(text)
    group = engine.cfg.groups[0]

    engine._handle(_incoming(BAD_SL_SELL, group, 1))

    assert broker.positions(engine.cfg.magic_number) == []
    assert [s.skipped_reason for s in db.signals_in_range(group.name, *WINDOW)] == ["sl_wrong_side"]
    assert alerts and "sl_wrong_side" in alerts[0]


def test_engine_sizes_lot_from_risk_percent(tmp_path: Path):
    engine, db, broker = _engine(tmp_path)
    engine.cfg.risk = RiskSettings(lot_mode="risk_percent", risk_percent=1.0)
    broker.set_balance(10_000)

    engine._handle(_incoming(SELL, engine.cfg.groups[0], 1))

    trades = db.trades_for_signal(db.active_signals()[0].id)
    assert len(trades) == 3
    assert all(t.lot == 0.03 for t in trades)


def test_engine_skips_when_min_lot_would_over_risk(tmp_path: Path):
    engine, db, broker = _engine(tmp_path)
    engine.cfg.risk = RiskSettings(lot_mode="risk_percent", risk_percent=1.0)
    broker.set_balance(100)
    group = engine.cfg.groups[0]

    engine._handle(_incoming(SELL, group, 1))

    assert broker.positions(engine.cfg.magic_number) == []
    assert [s.skipped_reason for s in db.signals_in_range(group.name, *WINDOW)] == ["risk_lot_unavailable"]


def _closed_loss(profit: float) -> TradeRecord:
    now = datetime.now(timezone.utc)
    return TradeRecord(
        id=None, ticket=999, signal_id="old", group_name="group_a", tp_index=4,
        tp_price=4300.0, lot=0.1, side="SELL", symbol="XAUUSD", received_at=now,
        entry_time=now, entry_price=4316.0, sl=4327.0, original_sl=4327.0,
        sl_moved_to_be=False, exit_time=now, exit_price=4327.0, close_reason="SL",
        profit=profit, pips=-110.0, status="closed",
    )


def test_daily_loss_limit_blocks_new_signals(tmp_path: Path):
    engine, db, broker = _engine(tmp_path)
    engine.cfg.risk = RiskSettings(daily_loss_limit=100)
    group = engine.cfg.groups[1]
    db.insert_trade(_closed_loss(-150.0))

    engine._handle(_incoming(SELL, group, 1))

    assert broker.positions(engine.cfg.magic_number) == []
    assert [s.skipped_reason for s in db.signals_in_range(group.name, *WINDOW)] == ["daily_loss_limit"]


def test_daily_loss_under_limit_still_trades(tmp_path: Path):
    engine, db, broker = _engine(tmp_path)
    engine.cfg.risk = RiskSettings(daily_loss_limit=100)
    db.insert_trade(_closed_loss(-40.0))

    engine._handle(_incoming(SELL, engine.cfg.groups[1], 1))

    assert len(broker.positions(engine.cfg.magic_number)) == 3


def test_risk_settings_hot_reload(tmp_path: Path):
    import yaml

    engine, _db, _broker = _engine(tmp_path)
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        yaml.safe_dump(
            {
                "telegram": {"groups": [{"name": "group_a", "chat_id": -1001, "lot": 0.01}]},
                "risk": {"sanity_checks": True, "daily_loss_limit": 250},
            }
        ),
        encoding="utf-8",
    )
    engine.cfg.config_path = cfg_file
    engine._cfg_mtime = 0.0
    engine._maybe_reload_settings()

    assert engine.cfg.risk.sanity_checks is True
    assert engine.cfg.risk.daily_loss_limit == 250
