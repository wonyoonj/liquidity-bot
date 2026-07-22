# -*- coding: utf-8 -*-
"""
Prevents the urgent signal scanner (lib/signal_scanner.py) from posting the
same story day after day. Since the underlying weekly-cadence series (TGA,
WALCL, RRP, WRESBAL, etc.) only actually change once a week, the exact same
signal (e.g. "TGA falling for 29 straight weeks") would otherwise fire and
get posted on every single run between data updates — this is the repeat-
content problem. Fix: remember which (ticker, signal_type) pairs were
recently posted and suppress reposting the same one for 14 days.

Same git-commit-based persistence trick as lib/news_state.py and
lib/github_image_host.py — a small JSON file committed back into the repo,
so state survives across separate GitHub Actions runs.

v2: record_signal_posted() now goes through
lib/git_sync.commit_and_push_with_retry instead of a single push attempt,
so a concurrent-write rejection from another workflow re-reads the latest
file and re-applies the update instead of silently dropping it.
"""
from __future__ import annotations

import os
import json
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

from lib.git_sync import commit_and_push_with_retry, GitSyncError

STATE_PATH = "state/posted_signals.json"
COOLDOWN_DAYS = 14


class SignalStateError(RuntimeError):
    pass


def _run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SignalStateError(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout.strip()


def _signal_key(ticker: str, signal_type: str) -> str:
    """Deliberately excludes the numeric value — 'TGA falling for 29 weeks'
    and 'TGA falling for 30 weeks' are the same underlying story to a reader,
    so they should be treated as one signal for dedup purposes."""
    return f"{ticker}:{signal_type}"


def is_on_cooldown(ticker: str, signal_type: str) -> bool:
    """True if this (ticker, signal_type) was posted within the last
    COOLDOWN_DAYS days and should therefore be skipped today."""
    if not os.path.exists(STATE_PATH):
        return False
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            records: Dict[str, str] = json.load(f)
    except Exception:
        return False

    key = _signal_key(ticker, signal_type)
    last_posted_str = records.get(key)
    if not last_posted_str:
        return False

    try:
        last_posted = datetime.fromisoformat(last_posted_str)
    except Exception:
        return False

    return datetime.now(timezone.utc) - last_posted < timedelta(days=COOLDOWN_DAYS)


def record_signal_posted(ticker: str, signal_type: str) -> None:
    """Marks (ticker, signal_type) as posted now, prunes anything older than
    COOLDOWN_DAYS, and commits+pushes. Non-fatal on failure — at worst a
    signal might repeat once, which is far better than crashing the run.

    Wraps the read-modify-write in `prepare` and hands it to
    commit_and_push_with_retry, which re-runs it against the
    freshly-pulled file if another workflow's push landed first."""
    def prepare() -> None:
        records: Dict[str, str] = {}
        if os.path.exists(STATE_PATH):
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                records = json.load(f)

        cutoff = datetime.now(timezone.utc) - timedelta(days=COOLDOWN_DAYS)
        records = {
            k: v for k, v in records.items()
            if _safe_parse(v) and _safe_parse(v) >= cutoff
        }
        records[_signal_key(ticker, signal_type)] = datetime.now(timezone.utc).isoformat()

        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    try:
        commit_and_push_with_retry(
            prepare_fn=prepare,
            add_paths=[STATE_PATH],
            commit_message="chore: record posted signal [skip ci]",
            branch=os.environ.get("GH_BRANCH", "main"),
        )
    except GitSyncError as e:
        print(f"[signal_state] WARN: could not persist state ({e}) — dedup may be imperfect next run.")
    except Exception as e:  # noqa: BLE001
        print(f"[signal_state] WARN: could not persist state ({e}) — dedup may be imperfect next run.")


def _safe_parse(iso_str: Optional[str]):
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str)
    except Exception:
        return None
