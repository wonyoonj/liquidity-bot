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
import re
import html
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

# Matches a bare "&" that is NOT already the start of a valid XML entity
# reference (&amp; &lt; &gt; &quot; &apos; &#123; &#x1F;) — real-world feeds,
# Reuters' included, routinely contain literal un-escaped ampersands in
# headline text (e.g. "S&P 500", "AT&T", "R&D"), which is invalid XML and
# makes feedparser's strict parser die with "not well-formed (invalid
# token)" and return ZERO entries — with no other symptom (no HTTP error,
# no bozo-free empty feed). Escaping any bare "&" to "&amp;" before parsing
# is the standard fix real-world RSS consumers apply for this extremely
# common feed-quality issue.
_BARE_AMPERSAND_RE = re.compile(r"&(?!#\d+;|#x[0-9a-fA-F]+;|[a-zA-Z][a-zA-Z0-9]*;)")


def _fetch_feed_entries(url: str, timeout: int = 20):
    """Fetches the feed ourselves via requests (with browser-like headers),
    sanitizes bare ampersands (see _BARE_AMPERSAND_RE above), and hands the
    cleaned text to feedparser.parse() — instead of calling
    feedparser.parse(url) directly, which gave us neither the real HTTP
    status code on a block nor a chance to fix the un-escaped-ampersand
    issue before the strict parser choked on it."""
    resp = requests.get(url, headers=_FEED_REQUEST_HEADERS, timeout=timeout)
    resp.raise_for_status()
    encoding = resp.encoding or resp.apparent_encoding or "utf-8"
    text = resp.content.decode(encoding, errors="replace")
    text = _BARE_AMPERSAND_RE.sub("&amp;", text)
    parsed = feedparser.parse(text)
    return parsed


# Google News RSS appends " - <Source Name>" to every title (e.g.
# "Fed holds rates steady - Reuters"). Strip that suffix so the LLM (and any
# future display of the raw title) sees a clean headline, not the source
# tag glued onto it.
_TITLE_SOURCE_SUFFIX_RE = re.compile(r"\s+-\s+[^-]{2,40}$")

# Google News RSS wraps each item's <description> in an HTML <a> link plus
# occasional extra markup rather than plain text — strip tags down to plain
# text before we use it as LLM context.
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _clean_google_news_title(raw_title: str) -> str:
    return _TITLE_SOURCE_SUFFIX_RE.sub("", raw_title).strip()


def _clean_summary_html(raw_summary: str) -> str:
    text = _HTML_TAG_RE.sub(" ", raw_summary)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    # Google News often tacks the bare source name onto the very end of the
    # description after tags are stripped (e.g. "...moderates. Reuters") —
    # drop a trailing "Reuters" token so it doesn't read as part of the story.
    text = re.sub(r"\s+Reuters\s*$", "", text, flags=re.IGNORECASE).strip()
    return text


def _entry_id(title: str) -> str:
    # Title-based (not link-based): Google News article links carry an
    # opaque per-request redirect token, which is far less stable across
    # separate fetches than the headline text itself — a link-based hash
    # would break same-story dedup between runs.
    return hashlib.sha256(title.strip().lower().encode("utf-8")).hexdigest()[:16]


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
            print(f"[top4_fetcher] WARN: Reuters (via Google News) feed returned 0 entries ({reason})", file=sys.stderr)
            return []
    except requests.exceptions.HTTPError as e:
        print(f"[top4_fetcher] WARN: Reuters (via Google News) feed request failed with HTTP "
              f"{e.response.status_code if e.response is not None else '?'}: {e}", file=sys.stderr)
        return []
    except requests.exceptions.RequestException as e:
        print(f"[top4_fetcher] WARN: Reuters (via Google News) feed request failed "
              f"({type(e).__name__}: {e})", file=sys.stderr)
        return []
    except Exception as e:  # noqa: BLE001
        print(f"[top4_fetcher] WARN: Reuters (via Google News) feed failed to load ({e})", file=sys.stderr)
        return []

    print(f"[top4_fetcher] Reuters (via Google News) feed OK — {len(parsed.entries)} raw entries returned")

    same_day: List[Dict] = []
    recent_fallback: List[Dict] = []
    seen_ids = set()

    for entry in parsed.entries[:max_entries]:
        raw_title = (entry.get("title") or "").strip()
        if not raw_title:
            continue
        title = _clean_google_news_title(raw_title)
        if not title:
            continue

        published = _parse_published(entry)
        if not published or published < cutoff:
            continue

        entry_id = _entry_id(title)
        if entry_id in seen_ids:
            continue
        seen_ids.add(entry_id)

        record = {
            "id": entry_id,
            "title": title,
            # only a short, plain-text snippet is ever kept — used as LLM
            # context only, never reproduced verbatim (same copyright-safe
            # design as news_fetcher.py)
            "summary": _clean_summary_html(entry.get("summary") or entry.get("description") or "")[:500],
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
