# -*- coding: utf-8 -*-
"""
Poll question bank (idea #1) + selection logic that matches this week's
economic calendar (idea #1 tied to CPI/FOMC/jobs day) or falls back to a
generic liquidity opinion poll (idea #10) when no major event is scheduled.
"""
from __future__ import annotations

import random
from typing import List, Dict, Optional, Tuple

# Keyed by the FRED release name used in fetch_calendar.py, so the poll
# matches whatever's actually on the calendar this week.
EVENT_POLLS: Dict[str, Tuple[str, List[str]]] = {
    "Consumer Price Index": (
        "This week's CPI print — how do you think it comes in?",
        ["Hotter than expected", "In line with expectations", "Cooler than expected", "Not sure / no view"],
    ),
    "Employment Situation": (
        "This week's jobs report — what's your read?",
        ["Stronger than expected", "In line", "Weaker than expected", "Not sure / no view"],
    ),
    "FOMC Press Release": (
        "This week's FOMC decision — what do you expect?",
        ["Rate hike", "Rate hold", "Rate cut", "Not sure / no view"],
    ),
    "Gross Domestic Product": (
        "This week's GDP print — how do you think it comes in?",
        ["Above expectations", "In line", "Below expectations", "Not sure / no view"],
    ),
    "Personal Income and Outlays": (
        "This week's PCE inflation data — what's your read?",
        ["Hotter than expected", "In line", "Cooler than expected", "Not sure / no view"],
    ),
}

# Idea #10: generic opinion polls when no major release is on the calendar this week.
GENERIC_LIQUIDITY_POLLS: List[Tuple[str, List[str]]] = [
    (
        "The Reverse Repo (RRP) balance has been trending down. How do you read that?",
        ["Genuine liquidity supply signal", "Temporary/technical move", "Not significant", "Not sure"],
    ),
    (
        "Where do you think net market liquidity flow heads over the next 4 weeks?",
        ["Turns more positive (supply)", "Turns more negative (drain)", "Stays roughly the same", "Not sure"],
    ),
    (
        "Which indicator do you personally watch most closely for market direction?",
        ["Fed balance sheet (WALCL)", "TGA balance", "Reverse Repo (RRP)", "MMF flows"],
    ),
    (
        "Do you think the Fed's current balance sheet policy is too tight, too loose, or about right?",
        ["Too tight", "Too loose", "About right", "Not sure"],
    ),
    (
        "How much does 'liquidity conditions' actually factor into your own trading/investing decisions?",
        ["A lot — I track it weekly", "Somewhat — I check occasionally", "Rarely", "Never"],
    ),
]


def pick_poll_for_week(calendar_events: List[Dict]) -> Tuple[str, List[str]]:
    """If a major event is on this week's calendar, ask about that. Otherwise
    fall back to a generic opinion poll (idea #10), rotated by week number so
    it doesn't repeat back-to-back."""
    for event in calendar_events:
        name = event.get("name")
        if name in EVENT_POLLS:
            return EVENT_POLLS[name]

    # No major release this week -> rotate through the generic bank.
    import datetime
    week_idx = datetime.date.today().isocalendar()[1] % len(GENERIC_LIQUIDITY_POLLS)
    return GENERIC_LIQUIDITY_POLLS[week_idx]


def pick_open_question_for_sunday() -> str:
    """A plain-text (non-poll) version for Threads, where native polls aren't
    supported by the API. Rotated the same way as the generic poll bank."""
    import datetime
    week_idx = datetime.date.today().isocalendar()[1] % len(GENERIC_LIQUIDITY_POLLS)
    question, _ = GENERIC_LIQUIDITY_POLLS[week_idx]
    return question
