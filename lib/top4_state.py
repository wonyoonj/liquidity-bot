# -*- coding: utf-8 -*-
"""
Persists which Top-4 stories have already been posted, so the same Reuters
story never gets picked twice across separate GitHub Actions runs.

Same "commit a small JSON file back into the repo" approach as
lib/news_state.py, kept as its OWN file/state path (state/posted_top4.json)
rather than sharing news_state.py's state/posted_news.json — the two
features draw from different source pools and should be deduped
independently. Rolling 45-day retention window, same as news_state.py.
"""
from __future__ import annotations

import os
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Set, Tuple

from lib.git_sync import commit_and_push_with_retry, GitSyncError

STATE_PATH = "state/posted_top4.json"
RETENTION_DAYS = 45


class Top4StateError(RuntimeError):
    pass


def load_posted_ids() -> Set[str]:
    """Returns the set of entry ids posted in the last RETENTION_DAYS days.
    Returns an empty set (never raises) if the state file doesn't exist yet
    — the normal situation on the very first run."""
    if not os.path.exists(STATE_PATH):
        return set()
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            records: List[Dict] = json.load(f)
    except Exception:
        return set()

    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    ids = set()
    for r in records:
        posted_at = _safe_parse(r.get("posted_at"))
        if posted_at and posted_at >= cutoff:
            ids.add(r["id"])
    return ids


def record_posted_many(entries: List[Tuple[str, str]]) -> None:
    """Appends ALL given (entry_id, title) pairs in a single read-modify-
    write + single commit/push — used to record all 4 picks from one run
    at once, instead of 4 separate commits (which would also mean 4x the
    chance of a concurrent-write race with other workflows).

    Non-fatal on failure: worst case a story might repeat once, which is
    far better than the whole daily post crashing over a git hiccup."""
    if not entries:
        return

    def prepare() -> None:
        records: List[Dict] = []
        if os.path.exists(STATE_PATH):
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                records = json.load(f)

        cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
        records = [r for r in records if _safe_parse(r.get("posted_at")) and _safe_parse(r["posted_at"]) >= cutoff]

        now_iso = datetime.now(timezone.utc).isoformat()
        for entry_id, title in entries:
            records.append({"id": entry_id, "title": title, "posted_at": now_iso})

        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    try:
        commit_and_push_with_retry(
            prepare_fn=prepare,
            add_paths=[STATE_PATH],
            commit_message="chore: record posted top4 headlines [skip ci]",
            branch=os.environ.get("GH_BRANCH", "main"),
        )
    except GitSyncError as e:
        print(f"[top4_state] WARN: could not persist state ({e}) — dedup may be imperfect next run.")
    except Exception as e:  # noqa: BLE001
        print(f"[top4_state] WARN: could not persist state ({e}) — dedup may be imperfect next run.")


def _safe_parse(iso_str):
    try:
        return datetime.fromisoformat(iso_str)
    except Exception:
        return None
