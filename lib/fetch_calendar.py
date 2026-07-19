# -*- coding: utf-8 -*-
"""
Fetches the upcoming week's major US economic release dates from FRED's
official Release Calendar API (fred/releases, fred/release/dates).

Requires a free FRED_API_KEY (instant, no approval needed):
    https://fred.stlouisfed.org/docs/api/api_key.html
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, date, timezone
from typing import List, Dict

import requests

FRED_API_BASE = "https://api.stlouisfed.org/fred"

TARGET_RELEASES = [
    "Employment Situation",
    "Consumer Price Index",
    "Personal Income and Outlays",
    "Gross Domestic Product",
    "FOMC Press Release",
]

NAME_LABEL = {
    "Employment Situation": "🧑‍💼 Employment Situation (Nonfarm Payrolls / Unemployment Rate)",
    "Consumer Price Index": "💰 CPI (Consumer Price Index)",
    "Personal Income and Outlays": "📊 PCE (Fed's preferred inflation gauge)",
    "Gross Domestic Product": "🏛️ GDP (Gross Domestic Product)",
    "FOMC Press Release": "🏦 FOMC Interest Rate Decision",
}

# Rough "how much does this typically move markets/liquidity expectations"
# ranking, used to pick the top-3 (and single most important) upcoming
# release for the Tuesday LLM commentary. FOMC (actual rate decisions) and
# the jobs/inflation reports the Fed watches most closely rank highest.
RELEASE_PRIORITY = {
    "FOMC Press Release": 5,
    "Employment Situation": 4,
    "Consumer Price Index": 4,
    "Personal Income and Outlays": 3,
    "Gross Domestic Product": 2,
}


def get_top_upcoming_events(events: List[Dict], n: int = 3) -> List[Dict]:
    """From get_events_this_month()'s output, returns the top-n UPCOMING
    (not yet past) events ranked by RELEASE_PRIORITY, then by soonest date.
    Used for the Tuesday 'here's what matters most this month' commentary."""
    upcoming = [e for e in events if not e["is_past"]]
    upcoming.sort(key=lambda e: (-RELEASE_PRIORITY.get(e["name"], 1), e["date"]))
    return upcoming[:n]

WEEKDAY_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class CalendarError(RuntimeError):
    pass


def _get_api_key() -> str:
    key = os.environ.get("FRED_API_KEY")
    if not key:
        raise CalendarError(
            "FRED_API_KEY is not set. Get a free key instantly at "
            "https://fred.stlouisfed.org/docs/api/api_key.html"
        )
    return key


def _resolve_release_ids(api_key: str, names: List[str], timeout: int = 20) -> Dict[str, int]:
    resp = requests.get(
        f"{FRED_API_BASE}/releases",
        params={"api_key": api_key, "file_type": "json", "limit": 1000},
        timeout=timeout,
    )
    resp.raise_for_status()
    releases = resp.json().get("releases", [])

    mapping: Dict[str, int] = {}
    for name in names:
        match = next(
            (r for r in releases if r.get("name", "").strip().lower() == name.strip().lower()),
            None,
        )
        if match:
            mapping[name] = match["id"]
    return mapping


def get_upcoming_releases(days_ahead: int = 7) -> List[Dict]:
    api_key = _get_api_key()
    id_map = _resolve_release_ids(api_key, TARGET_RELEASES)
    if not id_map:
        raise CalendarError("Could not resolve any target release_id from FRED.")

    today = datetime.now(timezone.utc).date()
    end_date = today + timedelta(days=days_ahead)

    upcoming: List[Dict] = []
    for name, release_id in id_map.items():
        resp = requests.get(
            f"{FRED_API_BASE}/release/dates",
            params={
                "release_id": release_id,
                "api_key": api_key,
                "file_type": "json",
                "realtime_start": today.isoformat(),
                "realtime_end": end_date.isoformat(),
                "include_release_dates_with_no_data": "true",
                "sort_order": "asc",
            },
            timeout=20,
        )
        resp.raise_for_status()
        for d in resp.json().get("release_dates", []):
            release_date = datetime.strptime(d["date"], "%Y-%m-%d").date()
            if today <= release_date <= end_date:
                upcoming.append({"name": name, "date": release_date})

    upcoming.sort(key=lambda x: x["date"])
    return upcoming


def get_events_this_month() -> List[Dict]:
    """All target releases within the CURRENT calendar month (1st through
    last day), including ones already past — used for the Tuesday 'this
    month's schedule' overview post (marks past events as done, upcoming
    ones as pending, so it reads as a full monthly outlook either way)."""
    api_key = _get_api_key()
    id_map = _resolve_release_ids(api_key, TARGET_RELEASES)
    if not id_map:
        raise CalendarError("Could not resolve any target release_id from FRED.")

    today = datetime.now(timezone.utc).date()
    month_start = today.replace(day=1)
    if today.month == 12:
        next_month_start = today.replace(year=today.year + 1, month=1, day=1)
    else:
        next_month_start = today.replace(month=today.month + 1, day=1)
    month_end = next_month_start - timedelta(days=1)

    events: List[Dict] = []
    for name, release_id in id_map.items():
        resp = requests.get(
            f"{FRED_API_BASE}/release/dates",
            params={
                "release_id": release_id,
                "api_key": api_key,
                "file_type": "json",
                "realtime_start": month_start.isoformat(),
                "realtime_end": month_end.isoformat(),
                "include_release_dates_with_no_data": "true",
                "sort_order": "asc",
            },
            timeout=20,
        )
        resp.raise_for_status()
        for d in resp.json().get("release_dates", []):
            release_date = datetime.strptime(d["date"], "%Y-%m-%d").date()
            if month_start <= release_date <= month_end:
                events.append({"name": name, "date": release_date, "is_past": release_date < today})

    events.sort(key=lambda x: x["date"])
    return events


def format_monthly_calendar_caption(events: List[Dict], site_url: str, why_it_matters: str = "") -> str:
    """No hashtags by design (see reach-strategy notes in daily_post.py).
    `why_it_matters` is the LLM-generated paragraph (see
    lib.llm_content.generate_calendar_commentary) explaining which upcoming
    release matters most this month and why — inserted between the full
    calendar list and the closing link."""
    today = datetime.now(timezone.utc).date()
    month_label = today.strftime("%B %Y")

    if not events:
        return (
            f"📅 <b>{month_label} — Major US Economic Releases</b>\n\n"
            "No major releases on the calendar this month — a quiet one.\n\n"
            f"👉 {site_url}"
        )

    lines = [f"📅 <b>{month_label} — Major US Economic Releases</b>\n"]
    for e in events:
        d: date = e["date"]
        weekday = WEEKDAY_EN[d.weekday()]
        label = NAME_LABEL.get(e["name"], e["name"])
        mark = "✅" if e["is_past"] else "🔜"
        lines.append(f"{mark} {d.strftime('%b %d')} ({weekday}) — {label}")

    if why_it_matters:
        lines.append("")
        lines.append(f"<i>Why it matters:</i> {why_it_matters}")

    lines.append("")
    lines.append(f"👉 {site_url}")
    return "\n".join(lines)


def format_weekly_calendar_caption(events: List[Dict], site_url: str) -> str:
    if not events:
        return (
            "📅 <b>This Week's Major US Economic Releases</b>\n\n"
            "No major releases scheduled this week — a quiet one.\n\n"
            f"👉 {site_url}"
        )

    lines = ["📅 <b>This Week's Major US Economic Releases</b>\n"]
    for e in events:
        d: date = e["date"]
        weekday = WEEKDAY_EN[d.weekday()]
        label = NAME_LABEL.get(e["name"], e["name"])
        lines.append(f"{d.strftime('%b %d')} ({weekday}) — {label}")

    lines.append(f"\n👉 {site_url}")
    return "\n".join(lines)
