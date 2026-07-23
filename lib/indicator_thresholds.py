# -*- coding: utf-8 -*-
"""
Explicit good/bad, and improving/worsening assessment for every indicator
this bot posts about (Wed/Thu knowledge posts + the urgent signal scanner).

WHY THIS EXISTS: feedback on an actual post (10Y-2Y spread, Wed knowledge
post) was that it reads like a data dashboard notification, not something
with a point of view — it gives a number and a definition, but never says
whether that number is good or bad, by what standard, or whether it's at
risk of getting worse. This module answers exactly those three questions,
from real computed data (never invented numbers), so every post — not just
one — can state:
    1. Is the CURRENT value good or bad for liquidity conditions, and by
       what explicit standard (a hard threshold where one genuinely
       exists, e.g. 0 for the yield curve; otherwise the trend direction
       this bot's own explainer text already calls liquidity-positive or
       -negative for that series).
    2. Is the recent trend improving or worsening.
    3. Is there a real risk of crossing into "bad" territory soon, based on
       the actual recent slope of the data — not a guess.

Two kinds of indicators need different treatment:
- Level-with-a-hard-threshold (spreads: 10Y-2Y, SOFR-EFFR, SOFR-IORB):
  there is a genuine, well-known dividing line where the *meaning* of the
  metric flips (e.g. positive curve vs inverted curve). Status is
  threshold-based.
- Trend-only indicators (TGA, WALCL, RRP, reserves, outright rate levels):
  there's no single "good number" — e.g. "$6.5T balance sheet" isn't
  inherently good or bad, only its DIRECTION relative to liquidity is.
  Status is derived from whether the recent trend is moving in the
  direction this bot's own explainer text already calls liquidity-positive
  or -negative for that series (mirrors signal_scanner.py's existing
  `higher_is_supply` field, so the judgment call here is never
  inconsistent with what the post itself explains elsewhere).
"""
from __future__ import annotations

from typing import Dict, List, Optional

# ticker -> True if a RISING value means MORE liquidity supplied (good);
# False if a RISING value means liquidity draining / conditions tightening
# (bad). Mirrors lib/signal_scanner.py's higher_is_supply field exactly, so
# a reader never sees the two disagree about the same series.
HIGHER_IS_GOOD: Dict[str, bool] = {
    "TGA": False,
    "WALCL": True,
    "RRP": False,
    "RESBAL": True,
    "FEDFUNDS": False,
    "SOFR": False,
    "IORB": False,
    "DPCREDIT": False,
    "DGS3MO": False,
    "DGS2": False,
    "DGS10": False,
    "RRPONTSYAWARD": False,
}

# Indicators with a genuine hard dividing line, where crossing it changes
# what the number MEANS (not just "higher/lower is better"). bad_if:
# which side of `value` counts as the risk/bad zone.
HARD_THRESHOLDS: Dict[str, Dict] = {
    "YIELD_SPREAD": {
        "value": 0.0, "bad_if": "below",
        "good_label": "Positive / normal-sloping curve",
        "bad_label": "Inverted curve — historically preceded most US recessions",
    },
    "SOFR_FEDFUNDS_SPREAD": {
        "value": 0.0, "bad_if": "above",
        "good_label": "SOFR trading at/below EFFR — normal funding conditions",
        "bad_label": "SOFR trading above EFFR — an early sign of funding-market stress",
    },
    "SOFR_IORB_SPREAD": {
        "value": 0.0, "bad_if": "above",
        "good_label": "SOFR trading at/below IORB — abundant reserve conditions",
        "bad_label": "SOFR trading above IORB — a classic signal that cash is getting scarce",
    },
    "USLIQ": {
        "value": 0.0, "bad_if": "below",
        "good_label": "Net positive — liquidity being supplied to markets",
        "bad_label": "Net negative — liquidity being drained from markets",
    },
}


def _slope(values: List[float]) -> float:
    """Second-half-average minus first-half-average — a simple, noise-
    resistant proxy for 'has this series been rising or falling lately',
    without needing an external stats library. Positive = rising trend."""
    n = len(values)
    if n < 4:
        return 0.0
    mid = n // 2
    first_avg = sum(values[:mid]) / mid
    second_avg = sum(values[mid:]) / (n - mid)
    return second_avg - first_avg


def assess(ticker: str, values: List[float], unit: str) -> Dict:
    """Returns a dict describing current status + trend risk for `ticker`,
    given the same `values` list (oldest -> newest) used to draw its chart.
    Never raises — degrades to an 'unknown' assessment if there isn't
    enough data or the ticker isn't recognized, so callers can always
    safely use the result."""
    empty = {"status": "unknown", "status_label": "", "trend": "unknown",
              "risk_note": "", "threshold": None}
    if not values or len(values) < 2:
        return empty

    current = values[-1]
    slope = _slope(values)
    scale = max((abs(v) for v in values), default=0) or 1.0
    if abs(slope) < scale * 0.01:
        trend = "flat"
    else:
        trend = "rising" if slope > 0 else "falling"

    threshold = HARD_THRESHOLDS.get(ticker)
    if threshold:
        bad_if = threshold["bad_if"]
        is_bad = (current < threshold["value"]) if bad_if == "below" else (current > threshold["value"])
        status = "bad" if is_bad else "good"
        status_label = threshold["bad_label"] if is_bad else threshold["good_label"]
        distance = abs(current - threshold["value"])
        moving_toward_bad = (slope < 0) if bad_if == "below" else (slope > 0)

        if status == "good" and moving_toward_bad:
            risk_note = (
                f"Currently {distance:.2f}{unit} on the safe side of the {threshold['value']:g}{unit} "
                f"line, but the recent trend has been moving toward it — if that pace continued, the "
                f"risk of crossing over would rise. Not there yet, but worth watching."
            )
        elif status == "good":
            risk_note = (
                f"Currently on the healthy side of the {threshold['value']:g}{unit} line, and the "
                f"recent trend has been moving further away from it, not toward it — near-term risk "
                f"of flipping looks low right now."
            )
        elif status == "bad" and moving_toward_bad:
            risk_note = (
                f"Already on the risk side of the {threshold['value']:g}{unit} line, and the recent "
                f"trend is pushing further in that direction — this looks like genuine deterioration, "
                f"not just noise."
            )
        else:
            risk_note = (
                f"Currently on the risk side of the {threshold['value']:g}{unit} line, but the recent "
                f"trend has been moving back toward it — an early sign of improvement, though it "
                f"hasn't crossed back yet."
            )
        return {"status": status, "status_label": status_label, "trend": trend,
                 "risk_note": risk_note, "threshold": threshold["value"]}

    higher_is_good = HIGHER_IS_GOOD.get(ticker)
    if higher_is_good is None:
        return {**empty, "trend": trend}

    if trend == "flat":
        status, status_label = "neutral", "Roughly stable over the shown window"
        risk_note = "No clear directional trend right now, so this indicator alone isn't adding near-term risk."
    else:
        moving_good = (trend == "rising") == higher_is_good
        if moving_good:
            status, status_label = "good", "Trending in the liquidity-supportive direction"
            risk_note = ("The recent trend is moving toward looser conditions, not tighter — near-term "
                          "risk of a liquidity squeeze from this indicator looks low right now.")
        else:
            status, status_label = "bad", "Trending in the liquidity-tightening direction"
            risk_note = ("The recent trend is moving toward tighter conditions. If this pace continues, "
                          "it adds to — not subtracts from — near-term liquidity-tightening risk.")

    return {"status": status, "status_label": status_label, "trend": trend,
             "risk_note": risk_note, "threshold": None}


STATUS_EMOJI = {"good": "🟢", "neutral": "🟡", "bad": "🔴", "unknown": ""}


def format_status_line(assessment: Dict) -> Optional[str]:
    """One-line, ready-to-paste caption fragment: emoji + status + risk
    note. Returns None if there's nothing usable to say (unknown ticker or
    insufficient data) so callers can skip the line entirely rather than
    print something empty."""
    if not assessment or assessment.get("status") in (None, "unknown"):
        return None
    emoji = STATUS_EMOJI.get(assessment["status"], "")
    label = assessment.get("status_label") or ""
    risk = assessment.get("risk_note") or ""
    if not label and not risk:
        return None
    line = f"{emoji} {label}".strip()
    if risk:
        line += f"\n{risk}"
    return line
