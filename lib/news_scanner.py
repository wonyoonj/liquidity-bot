# -*- coding: utf-8 -*-
"""
Orchestrates the daily news pick end-to-end:
    fetch RSS candidates -> drop already-posted stories -> ask the LLM to
    pick the single most liquidity-relevant one and write a short summary +
    impact line -> return it (or None if there's nothing new/relevant today).

Kept intentionally SEPARATE from lib/signal_scanner.py (the data-driven
record/streak scanner) rather than merged into one "mega scanner" — tying a
qualitative news story to a specific quantitative data signal reliably would
need the LLM to correctly link cause and effect across two very different
data types, which is a much harder and more error-prone problem than either
scanner alone. Keeping them independent, both firing on their own schedules,
is the more robust design.
"""
from __future__ import annotations

from typing import Optional, Dict

from lib.news_fetcher import fetch_candidate_entries
from lib.news_state import load_posted_ids, record_posted
from lib.llm_content import pick_and_write_news


def get_daily_news_pick(hours_back: int = 30) -> Optional[Dict]:
    print("[news_scanner] Fetching RSS candidates...")
    candidates = fetch_candidate_entries(hours_back=hours_back)
    print(f"  -> {len(candidates)} relevant candidates before dedup")

    already_posted = load_posted_ids()
    fresh = [c for c in candidates if c["id"] not in already_posted]
    print(f"  -> {len(fresh)} remaining after removing already-covered stories")

    if not fresh:
        return None

    # Cap the shortlist sent to the LLM — keeps the prompt small/cheap and
    # focuses on the freshest, highest-trust-weighted candidates.
    shortlist = fresh[:10]

    print("[news_scanner] Asking the LLM to pick + write the top story...")
    pick = pick_and_write_news(shortlist)
    if not pick:
        print("  -> LLM found nothing genuinely relevant today.")
        return None

    print(f"  -> picked: {pick['headline']}")
    return pick


def mark_news_posted(pick: Dict) -> None:
    record_posted(pick["id"], pick["title"])
