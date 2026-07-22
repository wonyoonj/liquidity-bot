# -*- coding: utf-8 -*-
"""
Persists which news stories have already been posted, so the same story
never gets covered twice — across separate GitHub Actions runs, which have
no memory of each other by default.

Uses the same "commit a small file back into the repo" trick as
lib/github_image_host.py, just for a JSON state file instead of an image.
Keeps a rolling 45-day window so the state file never grows unbounded.

v2: record_posted() now goes through lib/git_sync.commit_and_push_with_retry
instead of a single push attempt. If another workflow (daily_post.py,
refresh_threads_token.py) committed to the repo in between, the old code
just logged a WARN and silently dropped the update — meaning dedup state
could get lost on every race, not just "once in a while". Now, on a
rejected push, the latest remote file is re-read and our append is
re-applied on top of it before retrying, so the update is not lost.
"""
from __future__ import annotations

import os
import json
import subprocess
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Set

from lib.git_sync import commit_and_push_with_retry, GitSyncError

STATE_PATH = "state/posted_news.json"
RETENTION_DAYS = 45


class NewsStateError(RuntimeError):
    pass


def _run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise NewsStateError(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout.strip()


def load_posted_ids() -> Set[str]:
    """Returns the set of entry ids posted in the last RETENTION_DAYS days.
    Returns an empty set (never raises) if the state file doesn't exist yet
    — that's the normal situation on the very first run."""
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
        try:
            posted_at = datetime.fromisoformat(r["posted_at"])
            if posted_at >= cutoff:
                ids.add(r["id"])
        except Exception:
            continue
    return ids


def record_posted(entry_id: str, title: str) -> None:
    """Appends the given entry to the state file, prunes anything older than
    RETENTION_DAYS, and commits+pushes the result. Non-fatal on failure —
    worst case, a story might repeat once, which is far better than the
    whole daily post crashing over a git hiccup.

    The actual read-modify-write is wrapped in `prepare` and handed to
    commit_and_push_with_retry, which re-runs it against the freshly-pulled
    file if the push is rejected by a concurrent workflow — so a race no
    longer means the update just gets dropped."""
    def prepare() -> None:
        records: List[Dict] = []
        if os.path.exists(STATE_PATH):
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                records = json.load(f)

        cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
        records = [
            r for r in records
            if _safe_parse(r.get("posted_at")) and _safe_parse(r["posted_at"]) >= cutoff
        ]
        records.append({
            "id": entry_id,
            "title": title,
            "posted_at": datetime.now(timezone.utc).isoformat(),
        })

        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    try:
        commit_and_push_with_retry(
            prepare_fn=prepare,
            add_paths=[STATE_PATH],
            commit_message="chore: record posted news [skip ci]",
            branch=os.environ.get("GH_BRANCH", "main"),
        )
    except GitSyncError as e:
        print(f"[news_state] WARN: could not persist state ({e}) — dedup may be imperfect next run.")
    except Exception as e:  # noqa: BLE001
        print(f"[news_state] WARN: could not persist state ({e}) — dedup may be imperfect next run.")


def _safe_parse(iso_str):
    try:
        return datetime.fromisoformat(iso_str)
    except Exception:
        return None
