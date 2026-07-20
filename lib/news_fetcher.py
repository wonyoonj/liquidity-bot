# -*- coding: utf-8 -*-
"""
Fetches and parses all configured RSS feeds, returning a flat, deduplicated,
keyword-prefiltered list of recent candidate entries. Never raises on a
single bad feed — logs a warning and moves on, so one dead RSS URL never
takes down the whole run.
"""
from __future__ import annotations

import sys
import hashlib
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

import feedparser

from lib.news_sources import NEWS_SOURCES, RELEVANCE_KEYWORDS


def _entry_id(entry: dict) -> str:
    """Stable identifier for a news entry, used for dedup. Prefers the link
    (most stable across re-fetches); falls back to a hash of the title if a
    feed entry is missing one for some reason."""
    key = entry.get("link") or entry.get("title", "")
    return hashlib.sha256(key.strip().lower().encode("utf-8")).hexdigest()[:16]


def _normalized_title_words(title: str) -> set:
    stop = {"the", "a", "an", "to", "of", "in", "on", "for", "and", "is", "as", "at", "by"}
    words = "".join(c.lower() if c.isalnum() or c.isspace() else " " for c in title).split()
    return {w for w in words if w not in stop and len(w) > 2}


def _is_relevant(title: str, summary: str) -> bool:
    text = f"{title} {summary}".lower()
    return any(kw in text for kw in RELEVANCE_KEYWORDS)


def _parse_published(entry) -> Optional[datetime]:
    for field in ("published_parsed", "updated_parsed"):
        t = entry.get(field)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                continue
    return None


def fetch_candidate_entries(hours_back: int = 30, max_per_feed: int = 12) -> List[Dict]:
    """Pulls every configured feed, keeps only entries published within the
    last `hours_back` hours that match at least one relevance keyword.
    Returns entries newest-first, deduplicated by _entry_id (same story
    appearing in two feeds is kept once — whichever source it's found in
    first, feed list order = trust order)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    seen_ids: set = set()
    seen_title_words: List[set] = []
    candidates: List[Dict] = []

    for source in NEWS_SOURCES:
        try:
            parsed = feedparser.parse(source["url"])
            if parsed.bozo and not parsed.entries:
                raise ValueError(f"feed did not parse cleanly: {parsed.bozo_exception}")
        except Exception as e:  # noqa: BLE001
            print(f"[news_fetcher] WARN: skipping '{source['name']}' ({e})", file=sys.stderr)
            continue

        for entry in parsed.entries[:max_per_feed]:
            title = (entry.get("title") or "").strip()
            summary = (entry.get("summary") or entry.get("description") or "").strip()
            if not title:
                continue

            published = _parse_published(entry)
            if published and published < cutoff:
                continue  # too old, skip

            if not _is_relevant(title, summary):
                continue

            entry_id = _entry_id(entry)
            if entry_id in seen_ids:
                continue

            title_words = _normalized_title_words(title)
            is_near_duplicate = any(
                len(title_words & prev) / max(1, len(title_words | prev)) > 0.5
                for prev in seen_title_words
            )
            if is_near_duplicate:
                continue

            seen_ids.add(entry_id)
            seen_title_words.append(title_words)
            candidates.append({
                "id": entry_id,
                "title": title,
                "summary": summary[:500],  # cap length; only used as LLM context, never reproduced verbatim
                "link": entry.get("link", ""),
                "source_name": source["name"],
                "source_weight": source["weight"],
                "published": published.isoformat() if published else None,
            })

    candidates.sort(key=lambda c: (c["source_weight"], c["published"] or ""), reverse=True)
    return candidates
