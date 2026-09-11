from src.models import SignalRecord, TradeRecord
from src.stats import build_stats, max_tp_hit
from src.timeutil import utcnow


def _trade(signal_id, tp_index, reason="TP", status="closed", profit=1.0):
    now = utcnow()
    return TradeRecord(
        id=tp_index,
        ticket=1000 + tp_index,
        signal_id=signal_id,
        group_name="group_a",
        tp_index=tp_index,
        tp_price=4300 - tp_index,
        lot=0.01,
        side="SELL",
        symbol="XAUUSD",
        received_at=now,
        entry_time=now,
        entry_price=4316,
        sl=4327,
        original_sl=4327,
        sl_moved_to_be=False,
        exit_time=now,
        exit_price=4300,
        close_reason=reason,
        profit=profit,
        pips=10,
        status=status,
    )


def test_max_tp_hit():
    trades = [_trade("s1", i) for i in range(1, 4)]
    trades.append(_trade("s1", 4, reason="SL"))
    assert max_tp_hit(trades) == 3


def test_hit_percentages():
    now = utcnow()
    signals = [
        SignalRecord("a", "group_a", 1, 1, now, "XAUUSD", "SELL", 1, 2, 3, "", "completed", max_tp_hit=6),
        SignalRecord("b", "group_a", 1, 2, now, "XAUUSD", "SELL", 1, 2, 3, "", "completed", max_tp_hit=3),
        SignalRecord("c", "group_a", 1, 3, now, "XAUUSD", "SELL", 1, 2, 3, "", "completed", max_tp_hit=0),
    ]
    trades = []
    for i in range(1, 7):
        trades.append(_trade("a", i, reason="TP"))
    for i in range(1, 4):
        trades.append(_trade("b", i, reason="TP"))
    for i in range(1, 7):
        trades.append(_trade("c", i, reason="SL", profit=-1))

    stats = build_stats(signals, trades)
    assert stats["signals_completed"] == 3
    assert stats["hit_pct"][1] == 66.67
    assert stats["hit_pct"][3] == 66.67
    assert stats["hit_pct"][6] == 33.33
    assert stats["distribution"][0] == 1
    assert stats["distribution"][3] == 1
    assert stats["distribution"][6] == 1
