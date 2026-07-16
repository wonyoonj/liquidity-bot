# -*- coding: utf-8 -*-
"""
SUPERSEDED — this logic has been folded into lib/signal_scanner.py's
_scan_combined_metric(), which now competes on the same priority scale as
every individual liquidity/rate series (per the "urgent monitoring should
cover everything, not just liquidity" redesign). daily_post.py no longer
calls this module directly. Left in place for reference / in case you want
to call check_triggers() standalone somewhere.

Detects "event-triggered" conditions worth an immediate, off-schedule post:
streaks and record highs/lows. Pure computation over the history list
already produced by compute_net_market_flow_history() — no new data source
needed.
"""
from __future__ import annotations

from typing import List, Dict, Optional

STREAK_ALERT_THRESHOLD = 4     # weeks
RECORD_LOOKBACK_WEEKS = 26     # "record" = extreme within ~6 months


def _streak(values: List[float]) -> Dict:
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


def check_triggers(history: List[Dict]) -> List[str]:
    """Returns a list of caption strings for any triggers that fired this run.
    Empty list = nothing noteworthy happened, don't post anything extra."""
    if len(history) < 2:
        return []

    triggers: List[str] = []
    values = [h["net_market_flow"] for h in history]
    current = history[-1]
    current_val = current["net_market_flow"]

    # --- Idea #3: streak alert ---
    streak = _streak(values)
    if streak["length"] == STREAK_ALERT_THRESHOLD:  # fire exactly once, on the week it crosses the line
        direction_word = "supply" if streak["direction"] > 0 else "drain"
        emoji = "🔥" if streak["direction"] > 0 else "🥶"
        triggers.append(
            f"{emoji} <b>Streak Alert</b>\n\n"
            f"This is week {streak['length']} of a continuous liquidity {direction_word} streak "
            f"(as of {current['as_of_date']}). That's an unusually persistent run in one direction."
        )

    # --- Idea #6: record high/low within lookback window ---
    window = values[-RECORD_LOOKBACK_WEEKS:] if len(values) > RECORD_LOOKBACK_WEEKS else values
    if len(window) >= 6:  # need a meaningful sample before calling something a "record"
        if current_val == max(window) and current_val > 0:
            triggers.append(
                f"🏆 <b>Record Alert</b>\n\n"
                f"This week's net liquidity supply ({current_val:+.1f} B$/Week) is the strongest "
                f"in the past {len(window)} weeks (as of {current['as_of_date']})."
            )
        elif current_val == min(window) and current_val < 0:
            triggers.append(
                f"⚠️ <b>Record Alert</b>\n\n"
                f"This week's net liquidity drain ({current_val:+.1f} B$/Week) is the strongest "
                f"in the past {len(window)} weeks (as of {current['as_of_date']})."
            )

    # --- Direction flip (bonus): supply <-> drain transition, often the most shareable moment ---
    if len(values) >= 2:
        prev_dir = 1 if values[-2] >= 0 else -1
        cur_dir = 1 if values[-1] >= 0 else -1
        if prev_dir != cur_dir:
            new_state = "SUPPLY" if cur_dir > 0 else "DRAIN"
            triggers.append(
                f"🔄 <b>Turning Point</b>\n\n"
                f"Liquidity flow just flipped direction — this week moves into a "
                f"<b>{new_state}</b> phase ({current_val:+.1f} B$/Week, as of {current['as_of_date']})."
            )

    return triggers
