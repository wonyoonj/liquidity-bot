# -*- coding: utf-8 -*-
"""
Sunday content: turn the raw number into a "story" by comparing it against
recent history (e.g. "strongest supply in 6 months", "3rd biggest drain of
the past year"). Reuses compute_net_market_flow_history() — no new data source.
"""
from __future__ import annotations

from typing import List, Dict


def build_story_caption(history: List[Dict], site_url: str) -> str:
    if not history:
        return (
            "📈 <b>This Week in US Liquidity</b>\n\n"
            "Not enough historical data yet to build this week's story.\n\n"
            f"👉 {site_url}"
        )

    current = history[-1]
    current_val = current["net_market_flow"]
    n_weeks = len(history)

    values = [h["net_market_flow"] for h in history]
    rank_desc = sorted(values, reverse=True)  # strongest supply first
    rank_asc = sorted(values)                 # strongest drain first

    supply_rank = rank_desc.index(current_val) + 1
    drain_rank = rank_asc.index(current_val) + 1

    avg = sum(values) / len(values)
    diff_from_avg = current_val - avg

    lines = ["📈 <b>This Week in US Liquidity — By the Numbers</b>\n"]
    sign = "+" if current_val > 0 else ""
    lines.append(f"This week's net flow: <b>{sign}{current_val:.1f} B$/Week</b> ({current['as_of_date']})\n")

    if supply_rank == 1:
        lines.append(f"🏆 The strongest liquidity <b>supply</b> week in the past {n_weeks} weeks.")
    elif drain_rank == 1:
        lines.append(f"⚠️ The strongest liquidity <b>drain</b> week in the past {n_weeks} weeks.")
    elif supply_rank <= max(3, n_weeks // 10):
        lines.append(f"🔥 Ranks #{supply_rank} strongest supply week out of the last {n_weeks}.")
    elif drain_rank <= max(3, n_weeks // 10):
        lines.append(f"🥶 Ranks #{drain_rank} strongest drain week out of the last {n_weeks}.")
    else:
        direction = "above" if diff_from_avg > 0 else "below"
        lines.append(
            f"That's {abs(diff_from_avg):.1f} B$/Week {direction} the {n_weeks}-week average "
            f"of {avg:+.1f} B$/Week — a fairly typical week."
        )

    streak = _current_streak(values)
    if streak["length"] >= 3:
        direction_word = "supply" if streak["direction"] > 0 else "drain"
        lines.append(f"📊 This is week {streak['length']} of a continuous liquidity {direction_word} streak.")

    lines.append(f"\n👉 Full history: {site_url}")
    lines.append("#USLiquidity #FederalReserve #MarketLiquidity")
    return "\n".join(lines)


def _current_streak(values: List[float]) -> Dict:
    """Length of the current consecutive run of same-sign values, ending at the last entry."""
    if not values:
        return {"length": 0, "direction": 0}
    direction = 1 if values[-1] >= 0 else -1
    length = 0
    for v in reversed(values):
        v_dir = 1 if v >= 0 else -1
        if v_dir == direction:
            length += 1
        else:
            break
    return {"length": length, "direction": direction}
