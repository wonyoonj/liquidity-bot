# -*- coding: utf-8 -*-
"""
Persists which news stories have already been posted, so the same story
never gets covered twice — across separate GitHub Actions runs, which have
no memory of each other by default.

Uses the same "commit a small file back into the repo" trick as
lib/github_image_host.py, just for a JSON state file instead of an image.
Keeps a rolling 45-day window so the state file never grows unbounded.
"""
from __future__ import annotations

import os
import json
import subprocess
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Set

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
    whole daily post crashing over a git hiccup."""
    try:
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

        _run(["git", "config", "user.name", "liquidity-bot"])
        _run(["git", "config", "user.email", "liquidity-bot@users.noreply.github.com"])
        _run(["git", "add", STATE_PATH])

        diff_check = subprocess.run(["git", "diff", "--cached", "--quiet"])
        if diff_check.returncode == 0:
            return  # nothing changed, nothing to commit

        branch = os.environ.get("GH_BRANCH", "main")
        _run(["git", "commit", "-m", f"chore: record posted news [skip ci]"])
        _run(["git", "push", "origin", f"HEAD:{branch}"])
    except Exception as e:  # noqa: BLE001
        print(f"[news_state] WARN: could not persist state ({e}) — dedup may be imperfect next run.")


def _safe_parse(iso_str):
    try:
        return datetime.fromisoformat(iso_str)
    except Exception:
        return None
