# -*- coding: utf-8 -*-
"""
Wednesday content: an educational "what is this indicator and why does it
move liquidity/rates" post, shown alongside a 52-week chart of that
indicator. Rotates every week — odd ISO weeks pull from the LIQUIDITY
concept list, even ISO weeks pull from the RATES concept list, each list
cycling through its own items independently so the same topic doesn't
repeat until the whole list has been covered.

If the data doesn't go back a full 52 weeks, the chart simply uses
whatever history is available up to the most recent data point (see
_last_52_weeks below) instead of failing.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Tuple, Dict, Optional

Series = List[Tuple[datetime, float]]

# --- Liquidity concept rotation -----------------------------------------
LIQUIDITY_TOPICS = [
    {
        "key": "WTREGEN", "ticker": "TGA", "unit": "$B", "scale": 1 / 1000,
        "title": "What is the TGA (Treasury General Account)?",
        "explainer": (
            "The TGA is the US Treasury's checking account at the Fed. When it "
            "rises, the Treasury is pulling cash OUT of the banking system (via "
            "taxes or bond sales) and parking it at the Fed — that drains market "
            "liquidity. When it falls, the Treasury is spending that cash back "
            "into the economy — that supplies liquidity. Watching the TGA is one "
            "of the fastest ways to see liquidity shifts before they hit markets."
        ),
    },
    {
        "key": "WALCL", "ticker": "WALCL", "unit": "$B", "scale": 1 / 1000,
        "title": "What is the Fed's Balance Sheet (WALCL)?",
        "explainer": (
            "This is the total size of everything the Fed owns — mostly Treasuries "
            "and mortgage bonds bought during QE. A rising balance sheet means the "
            "Fed is creating new reserves and adding liquidity (QE). A falling "
            "balance sheet (like the current QT — quantitative tightening) means "
            "the Fed is letting bonds mature without replacing them, quietly "
            "draining liquidity from the system week by week."
        ),
    },
    {
        "key": "RRPONTSYD", "ticker": "RRP", "unit": "$B", "scale": 1,
        "title": "What is Reverse Repo (RRP)?",
        "explainer": (
            "The RRP facility is where money market funds and banks park excess "
            "cash overnight at the Fed in exchange for a safe, guaranteed yield. "
            "Think of it as a parking lot for idle cash. When RRP balances FALL, "
            "that cash is leaving the parking lot and flowing back into the "
            "banking system / markets — a liquidity supply signal. When RRP "
            "balances RISE, cash is being pulled off the sidelines and idled."
        ),
    },
    {
        "key": "WRESBAL", "ticker": "RESBAL", "unit": "$B", "scale": 1 / 1000,
        "title": "What are Bank Reserve Balances?",
        "explainer": (
            "Reserves are the cash banks hold directly at the Fed — the ultimate "
            "fuel for bank lending and market liquidity. When reserves are "
            "abundant, banks lend freely and financial conditions stay loose. "
            "When reserves get scarce (as QT drains them), funding markets can "
            "get tight fast — this is the metric the Fed watches most closely to "
            "know when QT has gone far enough."
        ),
    },
]

# --- Rate concept rotation ------------------------------------------------
# CONFIRMED against the real csvfile/ listing in the site's GitHub repo
# (checked July 2026) — these are the site's actual FRED codes.
RATE_TOPICS = [
    {
        "key": "FEDFUNDS", "ticker": "FEDFUNDS", "unit": "%", "scale": 1,
        "title": "What is the EFFR (Effective Fed Funds Rate)?",
        "explainer": (
            "This is the actual overnight rate banks pay each other, and it's "
            "the anchor for every other borrowing rate in the economy, from "
            "mortgages to credit cards. When it rises, borrowing gets more "
            "expensive everywhere and liquidity conditions tighten. When it "
            "falls, credit gets cheaper and easier to access, loosening "
            "liquidity conditions broadly."
        ),
    },
    {
        "key": "SOFR", "ticker": "SOFR", "unit": "%", "scale": 1,
        "title": "What is SOFR?",
        "explainer": (
            "SOFR (Secured Overnight Financing Rate) is the rate banks "
            "actually pay to borrow cash overnight against Treasury "
            "collateral — the real-world pulse of short-term funding "
            "markets. Sudden SOFR spikes above EFFR or IORB are an early "
            "warning that cash is getting scarce in the plumbing of the "
            "financial system, even before it shows up anywhere else."
        ),
    },
    {
        "key": "IORB", "ticker": "IORB", "unit": "%", "scale": 1,
        "title": "What is IORB (Interest on Reserve Balances)?",
        "explainer": (
            "IORB is the interest the Fed pays banks on the reserves they "
            "hold at the Fed. It's the floor of the Fed's rate corridor: "
            "banks won't lend for less than they can earn risk-free at the "
            "Fed. When money-market rates like SOFR trade below IORB, it "
            "signals liquidity is abundant; when SOFR pushes above IORB, "
            "it signals cash is getting tight."
        ),
    },
    {
        "key": "DPCREDIT", "ticker": "DPCREDIT", "unit": "%", "scale": 1,
        "title": "What is the Fed Discount Rate?",
        "explainer": (
            "This is the rate the Fed charges banks that borrow directly "
            "from its discount window — a backstop lending facility for "
            "when banks can't get funding elsewhere. It's rarely used in "
            "normal times, so a sudden jump in discount window borrowing "
            "(alongside this rate) is one of the clearest signals that "
            "liquidity has gotten tight somewhere in the banking system."
        ),
    },
    {
        "key": "DGS3MO", "ticker": "DGS3MO", "unit": "%", "scale": 1,
        "title": "What is the 3-Month Treasury Yield?",
        "explainer": (
            "This tracks what the US government pays to borrow for just "
            "three months, making it one of the most sensitive gauges of "
            "near-term Fed policy expectations and short-term liquidity "
            "conditions. It moves quickly around FOMC meetings and debt-"
            "ceiling events, often before other rates react."
        ),
    },
    {
        "key": "DGS2", "ticker": "DGS2", "unit": "%", "scale": 1,
        "title": "What is the 2-Year Treasury Yield?",
        "explainer": (
            "The 2-year yield reflects where markets expect the Fed Funds "
            "Rate to average over the next two years — it's the market's "
            "real-time vote on future Fed policy. It often moves BEFORE the "
            "Fed actually acts, making it one of the earliest signals of a "
            "coming shift in liquidity conditions."
        ),
    },
    {
        "key": "DGS10", "ticker": "DGS10", "unit": "%", "scale": 1,
        "title": "What is the 10-Year Treasury Yield?",
        "explainer": (
            "This is the benchmark for mortgage rates, corporate borrowing "
            "costs, and stock valuations worldwide. Rising yields mean "
            "tighter financial conditions (borrowing costs up, asset prices "
            "pressured); falling yields mean looser conditions."
        ),
    },
]

# Derived (not a raw CSV on the site — computed client-side there, mirrored
# here the same way from two already-fetched raw series). Rotated into the
# RATE_TOPICS pool as its own entry.
YIELD_SPREAD_TOPIC = {
    "derive": ("DGS10", "DGS2"), "ticker": "YIELD_SPREAD", "unit": "%", "scale": 1,
    "title": "What is the 10Y-2Y Yield Curve Spread?",
    "explainer": (
        "This is the gap between long-term and short-term Treasury yields. "
        "When it goes negative (an 'inverted' curve), it has historically "
        "signaled tight liquidity conditions and preceded most US "
        "recessions. When it steepens back into positive territory, it "
        "often marks the transition into an easier liquidity regime."
    ),
}
RATE_TOPICS.append(YIELD_SPREAD_TOPIC)


def _last_52_weeks(series: Series) -> Series:
    """Last 52 points if available; otherwise all available history back to
    the earliest data point (handles series with a shorter track record
    without ever failing)."""
    if not series:
        return []
    return series[-52:] if len(series) > 52 else series[:]


def _derive_series(data_store: dict, key_a: str, key_b: str) -> Optional[Series]:
    """Aligns two raw series by date and returns (date, value_a - value_b) —
    mirrors the site's client-side spread calculation (e.g. 10Y-2Y)."""
    series_a, series_b = data_store.get(key_a), data_store.get(key_b)
    if not series_a or not series_b:
        return None
    map_b = {d.date() if hasattr(d, "date") else d: v for d, v in series_b}
    spread = []
    for d, va in series_a:
        k = d.date() if hasattr(d, "date") else d
        if k in map_b:
            spread.append((d, va - map_b[k]))
    return spread if len(spread) >= 4 else None


def pick_topic_for_week(iso_week: int) -> Dict:
    """Alternates the pool by ISO-week parity (odd -> liquidity, even ->
    rates), and cycles independently through each pool so topics don't
    repeat until the full list has been covered."""
    if iso_week % 2 == 1:
        pool, pool_name = LIQUIDITY_TOPICS, "liquidity"
    else:
        pool, pool_name = RATE_TOPICS, "rates"

    idx = (iso_week // 2) % len(pool)
    topic = dict(pool[idx])
    topic["pool"] = pool_name
    return topic


def build_knowledge_content(data_store: dict, as_of: Optional[datetime] = None) -> Optional[Dict]:
    """Returns everything needed to render + caption the Wednesday knowledge
    card, or None if the chosen topic's series has no usable data this week
    (rare — falls back gracefully rather than posting a broken chart)."""
    as_of = as_of or datetime.utcnow()
    iso_week = as_of.isocalendar()[1]
    topic = pick_topic_for_week(iso_week)

    if "derive" in topic:
        series = _derive_series(data_store, *topic["derive"])
    else:
        series = data_store.get(topic["key"])

    if not series:
        return None

    points = _last_52_weeks(series)
    if len(points) < 4:
        return None

    values = [round(v * topic["scale"], 3) for _, v in points]
    dates = [d.strftime("%Y-%m-%d") for d, _ in points]

    return {
        "title": topic["title"],
        "explainer": topic["explainer"],
        "ticker": topic["ticker"],
        "unit": topic["unit"],
        "pool": topic["pool"],
        "chart_values": values,
        "chart_dates": dates,
        "current_value": values[-1],
        "weeks_shown": len(values),
    }
