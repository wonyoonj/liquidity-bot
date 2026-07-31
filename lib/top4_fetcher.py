# -*- coding: utf-8 -*-
"""
Fetches today's (US/Eastern calendar date) headlines from the Reuters
Business & Finance "best" RSS feed, for the daily "Top 4 Headlines" post.

Kept separate from lib/news_fetcher.py (which pulls from a whole LIST of
liquidity-focused sources and keyword-prefilters them) because this feature
has a different shape:
    - exactly ONE source (Reuters Business & Finance), per explicit request
    - no keyword prefilter — the feed itself is already scoped to
      business/finance, so everything in it is a valid candidate
    - "today" is defined by the US market's own calendar date (US/Eastern),
      not a rolling hours_back window, since the whole point of this
      feature is a once-a-day "here's today's top stories" digest dated in
      US time

Never raises on a feed error — logs a warning and returns an empty list,
so a dead/unreachable feed just means "nothing to post today" rather than
crashing the whole run (same fail-open philosophy as news_fetcher.py).
"""
from __future__ import annotations

import sys
import hashlib
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

import feedparser
import requests

from lib.news_sources import REUTERS_TOP4_FEED_URL
from lib.news_image import extract_feed_image_url

_EASTERN_STD_OFFSET = timedelta(hours=-5)  # EST
_EASTERN_DST_OFFSET = timedelta(hours=-4)  # EDT


def _nth_sunday_utc(year: int, month: int, n: int) -> datetime:
    d = datetime(year, month, 1, tzinfo=timezone.utc)
    first_sunday_day = 1 + (6 - d.weekday()) % 7
    return datetime(year, month, first_sunday_day + (n - 1) * 7, tzinfo=timezone.utc)


def _eastern_offset_for(dt_utc: datetime) -> timedelta:
    """US DST rule since 2007: starts 2nd Sunday in March, ends 1st Sunday
    in November (both transitions at 2am local time). Implemented with a
    plain fixed-offset approximation (no zoneinfo/tzdata dependency needed
    in this project) — accurate to the calendar date, which is all this
    feature needs; being off by an hour right at a DST transition boundary
    never changes which US calendar day a story falls on."""
    year = dt_utc.year
    dst_start = _nth_sunday_utc(year, 3, 2) + timedelta(hours=7)   # ~2am ET
    dst_end = _nth_sunday_utc(year, 11, 1) + timedelta(hours=6)    # ~2am ET
    return _EASTERN_DST_OFFSET if dst_start <= dt_utc < dst_end else _EASTERN_STD_OFFSET


def us_eastern_now() -> datetime:
    now_utc = datetime.now(timezone.utc)
    return now_utc + _eastern_offset_for(now_utc)


def us_today_label() -> str:
    """e.g. 'Jul 31, 2026' — used as the date line in the post caption."""
    return us_eastern_now().strftime("%b %-d, %Y")


_FEED_REQUEST_HEADERS = {
    # Reuters sits behind Cloudflare, which commonly 403s feedparser's
    # default User-Agent ("feedparser/x.x +https://feedparser.org/"). A
    # normal-browser UA avoids that block. This was the cause of the feed
    # silently returning 0 entries on early runs — always fetch the raw
    # bytes ourselves with these headers rather than letting feedparser.parse()
    # do its own (bot-flagged) request.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.7",
}


def _fetch_feed_entries(url: str, timeout: int = 20):
    """Fetches the feed ourselves via requests (with browser-like headers)
    and hands the raw bytes to feedparser.parse(), instead of calling
    feedparser.parse(url) directly. This gives us the actual HTTP status
    code / exception on failure to log, instead of feedparser silently
    swallowing a 403/timeout into an empty `entries` list with no clue why."""
    resp = requests.get(url, headers=_FEED_REQUEST_HEADERS, timeout=timeout)
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)
    return parsed


def _entry_id(entry: dict) -> str:
    key = entry.get("link") or entry.get("title", "")
    return hashlib.sha256(key.strip().lower().encode("utf-8")).hexdigest()[:16]


def _parse_published(entry) -> Optional[datetime]:
    for field in ("published_parsed", "updated_parsed"):
        t = entry.get(field)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                continue
    return None


def fetch_today_entries(max_entries: int = 25, fallback_hours: int = 36) -> List[Dict]:
    """Pulls the Reuters Business & Finance feed and returns entries
    published on TODAY's US/Eastern calendar date, newest first.

    If nothing strictly matches today's US date yet (e.g. it's still early
    US morning and Reuters hasn't published anything "today" in US terms),
    falls back to the most recent entries within the last `fallback_hours`
    hours instead of returning an empty list — this keeps the feature from
    going silent purely because of an edge-of-day timing gap, while
    dedup (see lib/top4_state.py) still prevents any repeat coverage."""
    today_et = us_eastern_now().date()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=fallback_hours)

    try:
        parsed = _fetch_feed_entries(REUTERS_TOP4_FEED_URL)
        if not parsed.entries:
            reason = getattr(parsed, "bozo_exception", None) or "feed parsed but contained 0 entries"
            print(f"[top4_fetcher] WARN: Reuters feed returned 0 entries ({reason})", file=sys.stderr)
            return []
    except requests.exceptions.HTTPError as e:
        print(f"[top4_fetcher] WARN: Reuters feed request failed with HTTP "
              f"{e.response.status_code if e.response is not None else '?'} "
              f"— likely blocked by Cloudflare/bot-protection: {e}", file=sys.stderr)
        return []
    except requests.exceptions.RequestException as e:
        print(f"[top4_fetcher] WARN: Reuters feed request failed ({type(e).__name__}: {e})", file=sys.stderr)
        return []
    except Exception as e:  # noqa: BLE001
        print(f"[top4_fetcher] WARN: Reuters feed failed to load ({e})", file=sys.stderr)
        return []

    print(f"[top4_fetcher] Reuters feed OK — {len(parsed.entries)} raw entries returned")

    same_day: List[Dict] = []
    recent_fallback: List[Dict] = []
    seen_ids = set()

    for entry in parsed.entries[:max_entries]:
        title = (entry.get("title") or "").strip()
        if not title:
            continue

        published = _parse_published(entry)
        if not published or published < cutoff:
            continue

        entry_id = _entry_id(entry)
        if entry_id in seen_ids:
            continue
        seen_ids.add(entry_id)

        record = {
            "id": entry_id,
            "title": title,
            # only a short snippet is ever kept — used as LLM context only,
            # never reproduced verbatim (same copyright-safe design as
            # news_fetcher.py)
            "summary": (entry.get("summary") or entry.get("description") or "").strip()[:500],
            "link": entry.get("link", ""),
            "image_url": extract_feed_image_url(entry),
            "source_name": "Reuters",
            "published": published.isoformat(),
        }
        recent_fallback.append(record)

        if (published + _eastern_offset_for(published)).date() == today_et:
            same_day.append(record)

    print(f"[top4_fetcher] {len(same_day)} entries dated today (US/Eastern: {today_et}), "
          f"{len(recent_fallback)} within last {fallback_hours}h as fallback pool")
    return same_day if same_day else recent_fallback
