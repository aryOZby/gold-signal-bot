from __future__ import annotations

from collections import defaultdict

from .models import SignalRecord, TradeRecord


def max_tp_hit(trades: list[TradeRecord]) -> int:
    hits = [
        t.tp_index
        for t in trades
        if t.status == "closed" and (t.close_reason or "").upper() == "TP"
    ]
    return max(hits) if hits else 0


def build_stats(signals: list[SignalRecord], trades: list[TradeRecord]) -> dict:
    by_signal: dict[str, list[TradeRecord]] = defaultdict(list)
    for trade in trades:
        by_signal[trade.signal_id].append(trade)

    completed = [s for s in signals if s.status == "completed"]
    skipped = [s for s in signals if s.status == "skipped"]
    failed = [s for s in signals if s.status == "failed"]
    active = [s for s in signals if s.status == "active"]

    max_levels = 0
    for group in by_signal.values():
        if group:
            max_levels = max(max_levels, max(t.tp_index for t in group))

    hit_counts: dict[int, int] = {}
    distribution: dict[int, int] = {0: 0}
    profits = []
    for signal in completed:
        group = by_signal.get(signal.id, [])
        level = signal.max_tp_hit if signal.max_tp_hit is not None else max_tp_hit(group)
        distribution[level] = distribution.get(level, 0) + 1
        for n in range(1, max_levels + 1):
            if level >= n:
                hit_counts[n] = hit_counts.get(n, 0) + 1
        closed_profit = sum(t.profit or 0.0 for t in group if t.status == "closed")
        profits.append(closed_profit)

    total_completed = len(completed) or 1
    hit_pct = {
        n: round(100.0 * hit_counts.get(n, 0) / len(completed), 2) if completed else 0.0
        for n in range(1, max_levels + 1)
    }
    dist_pct = {
        k: round(100.0 * v / len(completed), 2) if completed else 0.0
        for k, v in sorted(distribution.items())
    }

    return {
        "signals_total": len(signals),
        "signals_completed": len(completed),
        "signals_active": len(active),
        "signals_skipped": len(skipped),
        "signals_failed": len(failed),
        "max_tp_levels": max_levels,
        "hit_counts": hit_counts,
        "hit_pct": hit_pct,
        "distribution": distribution,
        "distribution_pct": dist_pct,
        "profit_total": round(sum(profits), 2),
        "profit_avg": round(sum(profits) / total_completed, 2) if completed else 0.0,
        "denominator": len(completed),
    }
