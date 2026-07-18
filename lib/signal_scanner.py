# -*- coding: utf-8 -*-
"""
UNIFIED urgent scanner. Runs every single day regardless of the weekday
content schedule, and covers EVERYTHING the site monitors — not just
liquidity:
    1. Each raw liquidity series (TGA, Fed balance sheet, RRP, bank reserves)
    2. Each raw rate series (Fed Funds, 10Y, 2Y, 10Y-2Y spread, SOFR) — if
       your site/API supports them (see lib/fetch_data.py OPTIONAL_RATE_INDICATORS)
    3. The combined net-liquidity-flow metric itself (streak / record /
       turning-point — this replaces the old lib/triggers.py, folded in here
       so everything competes on one shared priority scale)

Across ALL of the above, only the single MOST notable signal is posted per
run (Barchart-style: one sharp fact, not a wall of alerts). If nothing is
genuinely notable today, nothing posts — this is intentional.

Design choice: everything here is pure data logic, no LLM call — the LLM
(see lib/llm_content.py's generate_fact_caption) only phrases the *already
computed* fact into a sentence. This guarantees every claim is numerically
grounded and never hallucinated.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Tuple, Dict, Optional

Series = List[Tuple[datetime, float]]

# --- Raw series to scan individually -----------------------------------
# 'higher_is_supply' = which direction of movement means "more liquidity
# supplied to the market" for that series (used only for framing/labels).
LIQUIDITY_SCAN_TARGETS = [
    {"key": "WTREGEN", "label": "TGA Balance", "ticker": "TGA", "unit": "$B",
     "scale": 1 / 1000, "higher_is_supply": False, "category": "liquidity"},
    {"key": "WALCL", "label": "Fed Total Assets", "ticker": "WALCL", "unit": "$B",
     "scale": 1 / 1000, "higher_is_supply": True, "category": "liquidity"},
    {"key": "RRPONTSYD", "label": "Reverse Repo (RRP) Balance", "ticker": "RRP", "unit": "$B",
     "scale": 1, "higher_is_supply": False, "category": "liquidity"},
    {"key": "WRESBAL", "label": "Bank Reserve Balances", "ticker": "RESBAL", "unit": "$B",
     "scale": 1 / 1000, "higher_is_supply": True, "category": "liquidity"},
]

# Optional — only scanned if present in data_store (see fetch_data.py).
# CONFIRMED against the real csvfile/ listing in the site's GitHub repo.
RATE_SCAN_TARGETS = [
    {"key": "FEDFUNDS", "label": "EFFR (Effective Fed Funds Rate)", "ticker": "FEDFUNDS", "unit": "%",
     "scale": 1, "higher_is_supply": False, "category": "rates"},
    {"key": "SOFR", "label": "SOFR", "ticker": "SOFR", "unit": "%",
     "scale": 1, "higher_is_supply": False, "category": "rates"},
    {"key": "IORB", "label": "IORB (Interest on Reserve Balances)", "ticker": "IORB", "unit": "%",
     "scale": 1, "higher_is_supply": False, "category": "rates"},
    {"key": "DPCREDIT", "label": "Fed Discount Rate", "ticker": "DPCREDIT", "unit": "%",
     "scale": 1, "higher_is_supply": False, "category": "rates"},
    {"key": "DGS3MO", "label": "3-Month Treasury Yield", "ticker": "DGS3MO", "unit": "%",
     "scale": 1, "higher_is_supply": False, "category": "rates"},
    {"key": "DGS2", "label": "2-Year Treasury Yield", "ticker": "DGS2", "unit": "%",
     "scale": 1, "higher_is_supply": False, "category": "rates"},
    {"key": "DGS10", "label": "10-Year Treasury Yield", "ticker": "DGS10", "unit": "%",
     "scale": 1, "higher_is_supply": False, "category": "rates"},
    {"key": "RRPONTSYAWARD", "label": "RRP Award Rate", "ticker": "RRPONTSYAWARD", "unit": "%",
     "scale": 1, "higher_is_supply": False, "category": "rates"},
]

# The site computes these AS SPREADS client-side (no raw CSV exists for
# them) — mirrored here the same way, built from two already-fetched raw
# series rather than fetched directly.
DERIVED_SPREAD_TARGETS = [
    {"a": "DGS10", "b": "DGS2", "label": "10Y-2Y Yield Curve Spread", "ticker": "YIELD_SPREAD"},
    {"a": "SOFR", "b": "FEDFUNDS", "label": "SOFR-EFFR Spread", "ticker": "SOFR_FEDFUNDS_SPREAD"},
    {"a": "SOFR", "b": "IORB", "label": "SOFR-IORB Spread", "ticker": "SOFR_IORB_SPREAD"},
]

SCAN_TARGETS = LIQUIDITY_SCAN_TARGETS + RATE_SCAN_TARGETS

LOOKBACK_WEEKS = 52          # "record" window ≈ 1 year of weekly prints
STREAK_MIN_TO_REPORT = 4     # weeks
BIG_MOVE_PERCENTILE = 0.90   # top 10% weekly move size vs trailing history

STREAK_ALERT_THRESHOLD = 4      # weeks, for the combined net-flow metric
RECORD_LOOKBACK_WEEKS = 26      # weeks, for the combined net-flow metric


def _weekly_points(series: Series, n: int) -> List[Tuple[datetime, float]]:
    return series[-n:] if len(series) > n else series[:]


def _streak(diffs: List[float]) -> Dict:
    if not diffs:
        return {"length": 0, "direction": 0}
    direction = 1 if diffs[-1] >= 0 else -1
    length = 0
    for d in reversed(diffs):
        d_dir = 1 if d >= 0 else -1
        if d_dir == direction:
            length += 1
        else:
            break
    return {"length": length, "direction": direction}


def _scan_one_series(data_store: dict, target: dict) -> Optional[Dict]:
    series = data_store.get(target["key"])
    if not series or len(series) < 8:
        return None

    points = _weekly_points(series, LOOKBACK_WEEKS)
    values = [v * target["scale"] for _, v in points]
    dates = [d for d, _ in points]
    if len(values) < 8:
        return None

    diffs = [values[i] - values[i - 1] for i in range(1, len(values))]
    current_val = values[-1]
    current_diff = diffs[-1]
    current_date = dates[-1]

    candidates: List[Dict] = []

    if current_val == max(values):
        candidates.append({
            "type": "level_record_high", "priority": 3,
            "text": f"{target['label']} just hit its highest level in {len(values)} weeks.",
        })
    elif current_val == min(values):
        candidates.append({
            "type": "level_record_low", "priority": 3,
            "text": f"{target['label']} just hit its lowest level in {len(values)} weeks.",
        })

    streak = _streak(diffs)
    if streak["length"] >= STREAK_MIN_TO_REPORT:
        direction_word = "rising" if streak["direction"] > 0 else "falling"
        candidates.append({
            "type": "streak", "priority": 2 + min(streak["length"] // 4, 2),
            "text": f"{target['label']} has been {direction_word} for {streak['length']} "
                    f"straight weeks — its longest run in recent memory.",
        })

    if len(diffs) >= 10:
        abs_diffs = sorted(abs(d) for d in diffs[:-1])
        threshold_idx = int(len(abs_diffs) * BIG_MOVE_PERCENTILE)
        threshold = abs_diffs[min(threshold_idx, len(abs_diffs) - 1)]
        if abs(current_diff) > 0 and abs(current_diff) >= threshold and threshold > 0:
            direction_word = "jumped" if current_diff > 0 else "dropped"
            candidates.append({
                "type": "big_move", "priority": 2,
                "text": f"{target['label']} just {direction_word} {abs(current_diff):.2f}{target['unit']} "
                        f"in a single week — one of its sharpest moves in the past {len(diffs)} weeks.",
            })

    if not candidates:
        return None

    best = max(candidates, key=lambda c: c["priority"])
    return {
        "series_key": target["key"],
        "label": target["label"],
        "ticker": target["ticker"],
        "unit": target["unit"],
        "category": target["category"],
        "signal_type": best["type"],
        "priority": best["priority"],
        "fact_text": best["text"],
        "current_value": round(current_val, 2),
        "current_date": current_date.strftime("%Y-%m-%d"),
        "chart_values": [round(v, 2) for v in values],
        "chart_dates": [d.strftime("%Y-%m-%d") for d in dates],
    }


def _build_spread_series(data_store: dict, key_a: str, key_b: str) -> Optional[Series]:
    """Aligns two raw series by date and returns (date, value_a - value_b) —
    used to mirror the site's client-side spread calculations (10Y-2Y,
    SOFR-EFFR, SOFR-IORB) without needing a raw CSV for the spread itself."""
    series_a, series_b = data_store.get(key_a), data_store.get(key_b)
    if not series_a or not series_b:
        return None
    map_b = {d.date() if hasattr(d, "date") else d: v for d, v in series_b}
    spread = []
    for d, va in series_a:
        k = d.date() if hasattr(d, "date") else d
        if k in map_b:
            spread.append((d, va - map_b[k]))
    return spread if len(spread) >= 8 else None


def _scan_derived_spreads(data_store: dict) -> List[Dict]:
    results = []
    for t in DERIVED_SPREAD_TARGETS:
        spread_series = _build_spread_series(data_store, t["a"], t["b"])
        if not spread_series:
            continue
        temp_store = {"_SPREAD": spread_series}
        target = {"key": "_SPREAD", "label": t["label"], "ticker": t["ticker"],
                  "unit": "%", "scale": 1, "higher_is_supply": False, "category": "rates"}
        signal = _scan_one_series(temp_store, target)
        if signal:
            results.append(signal)
    return results


def _scan_combined_metric(data_store: dict) -> Optional[Dict]:
    """Folds in the old lib/triggers.py logic (streak / record / turning
    point) for the combined net-liquidity-flow metric, so it competes on the
    same priority scale as every individual series above."""
    from lib.compute_liquidity import compute_net_market_flow_history

    try:
        history = compute_net_market_flow_history(data_store, weeks=RECORD_LOOKBACK_WEEKS + 5)
    except Exception:
        return None
    if len(history) < 6:
        return None

    values = [h["net_market_flow"] for h in history]
    current = history[-1]
    current_val = current["net_market_flow"]
    candidates: List[Dict] = []

    streak = _streak(values)
    if streak["length"] >= STREAK_ALERT_THRESHOLD:
        direction_word = "supply" if streak["direction"] > 0 else "drain"
        candidates.append({
            "type": "combined_streak", "priority": 2 + min(streak["length"] // 4, 2),
            "text": f"Net US market liquidity has been in a {direction_word} streak for "
                    f"{streak['length']} straight weeks — an unusually persistent run.",
        })

    window = values[-RECORD_LOOKBACK_WEEKS:] if len(values) > RECORD_LOOKBACK_WEEKS else values
    if len(window) >= 6:
        if current_val == max(window) and current_val > 0:
            candidates.append({
                "type": "combined_record_high", "priority": 3,
                "text": f"This week's net liquidity supply ({current_val:+.1f} B$/Week) is the "
                        f"strongest in {len(window)} weeks.",
            })
        elif current_val == min(window) and current_val < 0:
            candidates.append({
                "type": "combined_record_low", "priority": 3,
                "text": f"This week's net liquidity drain ({current_val:+.1f} B$/Week) is the "
                        f"strongest in {len(window)} weeks.",
            })

    if len(values) >= 2:
        prev_dir = 1 if values[-2] >= 0 else -1
        cur_dir = 1 if values[-1] >= 0 else -1
        if prev_dir != cur_dir:
            new_state = "SUPPLY" if cur_dir > 0 else "DRAIN"
            candidates.append({
                "type": "combined_turning_point", "priority": 3,
                "text": f"Net US market liquidity flow just flipped into a {new_state} phase "
                        f"({current_val:+.1f} B$/Week).",
            })

    if not candidates:
        return None

    best = max(candidates, key=lambda c: c["priority"])
    chart_values = [round(v, 1) for v in values]
    chart_dates = [h["as_of_date"] for h in history]
    return {
        "series_key": "NET_MARKET_FLOW",
        "label": "Net US Market Liquidity",
        "ticker": "USLIQ",
        "unit": "B$/Wk",
        "category": "liquidity",
        "signal_type": best["type"],
        "priority": best["priority"],
        "fact_text": best["text"],
        "current_value": round(current_val, 1),
        "current_date": current["as_of_date"],
        "chart_values": chart_values,
        "chart_dates": chart_dates,
    }


def scan_for_signals(data_store: dict) -> List[Dict]:
    """Every candidate signal across liquidity series, rate series, and the
    combined metric — sorted by priority descending. Index 0 is the single
    most 'urgent, worth an off-schedule post' fact today."""
    results = []
    for target in SCAN_TARGETS:
        signal = _scan_one_series(data_store, target)
        if signal:
            results.append(signal)

    combined = _scan_combined_metric(data_store)
    if combined:
        results.append(combined)

    results.extend(_scan_derived_spreads(data_store))

    results.sort(key=lambda s: s["priority"], reverse=True)
    return results


def get_top_signal(data_store: dict) -> Optional[Dict]:
    signals = scan_for_signals(data_store)
    return signals[0] if signals else None
