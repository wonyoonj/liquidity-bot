# -*- coding: utf-8 -*-
"""
Shared "commit a file back into the repo" helper for github_image_host.py,
news_state.py and signal_state.py.

WHY THIS EXISTS (v8 fix):
Every one of those three modules independently does git add/commit/push
against the SAME repo/branch. daily_post.py alone can call the image
publisher twice in one run (calendar card + signal card), and separately
daily_news.py and refresh_threads_token.py run as their own workflows.
When two of these land within the same few seconds — which the logs show
is exactly what happened —  the second `git push` is rejected:

    ! [rejected]        HEAD -> main (fetch first)
    hint: Updates were rejected because the remote contains work that you
    hint: do not have locally.

That's not a permissions/CDN problem (those were fixed in earlier
versions) — it's a plain optimistic-concurrency race. The old code treated
any non-zero push exit as fatal and fell back to text-only. This module
adds real retry: on a rejected push, pull the latest remote state and
re-apply the change, instead of giving up.

Two different retry strategies are exposed because the two use cases need
different conflict handling:

- Images (github_image_host.py): each file is a brand-new, uniquely-named
  file, so there is never real content to merge — `git rebase` onto the new
  remote tip always applies cleanly. See `push_with_retry`.

- JSON state files (news_state.py, signal_state.py): two concurrent runs
  can both append to the *same* file, which is exactly the kind of textual
  edit `git rebase` can conflict on. Instead of resolving a text conflict,
  it's simpler and safer to throw the local commit away, re-read the
  now-current remote file, re-apply our logical change (append/prune) on
  top of it, and recommit. That's what `commit_and_push_with_retry` does
  via the caller-supplied `prepare_fn`.
"""
from __future__ import annotations

import os
import time
import random
import subprocess
from typing import Callable, Iterable, List


class GitSyncError(RuntimeError):
    pass


def run(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(f"    $ {' '.join(cmd)}")
    if result.stdout.strip():
        print(f"      stdout: {result.stdout.strip()}")
    if result.stderr.strip():
        print(f"      stderr: {result.stderr.strip()}")
    if check and result.returncode != 0:
        raise GitSyncError(f"Command failed ({result.returncode}): {' '.join(cmd)}\n{result.stderr}")
    return result


def configure_identity() -> None:
    run(["git", "config", "user.name", "liquidity-bot"])
    run(["git", "config", "user.email", "liquidity-bot@users.noreply.github.com"])


def _is_conflict_rejection(stderr: str) -> bool:
    s = stderr.lower()
    return "rejected" in s or "non-fast-forward" in s or "fetch first" in s


def _nothing_staged() -> bool:
    return subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0


def push_with_retry(branch: str, max_attempts: int = 5, base_delay: float = 2.0) -> None:
    """Pushes the current HEAD to `branch`. On a "rejected/fetch first"
    conflict (another workflow pushed in between), fetches + rebases HEAD
    onto the new remote tip and retries. Use this after a commit that adds
    a uniquely-named file (e.g. a timestamped image) where a rebase can
    never produce a real merge conflict.

    Raises GitSyncError on any non-conflict push failure (auth, branch
    protection, etc.) immediately — those are not retryable — or after
    exhausting max_attempts on a genuine content conflict.
    """
    delay = base_delay
    for attempt in range(1, max_attempts + 1):
        push_result = run(["git", "push", "origin", f"HEAD:{branch}"], check=False)
        if push_result.returncode == 0:
            if attempt > 1:
                print(f"    push succeeded on attempt {attempt} after rebase retry")
            return

        if not _is_conflict_rejection(push_result.stderr):
            raise GitSyncError(
                f"git push FAILED (exit {push_result.returncode}) — this is NOT a concurrency "
                f"conflict (no 'rejected'/'fetch first' in stderr), so retrying won't help. "
                f"Check branch protection rules / token permissions.\n{push_result.stderr}"
            )

        print(f"    push rejected (attempt {attempt}/{max_attempts}) — another workflow pushed "
              f"first, fetching + rebasing and retrying...")
        if attempt == max_attempts:
            break

        run(["git", "fetch", "origin", branch])
        rebase_result = run(["git", "rebase", f"origin/{branch}"], check=False)
        if rebase_result.returncode != 0:
            run(["git", "rebase", "--abort"], check=False)
            raise GitSyncError(
                f"git rebase onto origin/{branch} failed — this is a real content conflict, "
                f"not just a race, so it needs manual resolution.\n{rebase_result.stderr}"
            )
        time.sleep(delay + random.uniform(0, 1.0))
        delay = min(delay * 1.8, 12.0)

    raise GitSyncError(
        f"git push to {branch} still rejected after {max_attempts} attempts — the repo is under "
        f"heavier concurrent write load than this can absorb. Consider staggering workflow "
        f"schedules further apart."
    )


def commit_and_push_with_retry(
    prepare_fn: Callable[[], None],
    add_paths: Iterable[str],
    commit_message: str,
    branch: str | None = None,
    max_attempts: int = 5,
    base_delay: float = 2.0,
) -> bool:
    """Runs prepare_fn() to (re)write the file(s) at add_paths based on
    whatever is currently on disk, stages + commits + pushes them. If the
    push is rejected due to a concurrent write from another workflow, this
    throws away the local commit, hard-resets to the new remote tip, and
    calls prepare_fn() again — so on retry it re-reads the *now-current*
    (just-pulled) state file and re-applies the same logical change on top
    of it, rather than trying to text-merge two concurrent edits to the
    same JSON file.

    prepare_fn must be safe to call more than once and must always (over)
    write add_paths from current on-disk contents — it should not rely on
    in-memory state from a previous call, since that state may now be stale.

    Returns True if a commit was pushed, False if there was nothing to
    commit (file content unchanged). Raises GitSyncError on a non-recoverable
    push failure or after exhausting max_attempts.
    """
    branch = branch or os.environ.get("GH_BRANCH", "main")
    add_paths = list(add_paths)
    configure_identity()

    delay = base_delay
    for attempt in range(1, max_attempts + 1):
        prepare_fn()
        for p in add_paths:
            run(["git", "add", p])

        if _nothing_staged():
            return False

        run(["git", "commit", "-m", commit_message])
        push_result = run(["git", "push", "origin", f"HEAD:{branch}"], check=False)
        if push_result.returncode == 0:
            if attempt > 1:
                print(f"    push succeeded on attempt {attempt} after reload retry")
            return True

        if not _is_conflict_rejection(push_result.stderr):
            raise GitSyncError(
                f"git push FAILED (exit {push_result.returncode}) — not a concurrency conflict, "
                f"retrying won't help. Check branch protection rules / token permissions.\n"
                f"{push_result.stderr}"
            )

        print(f"    push rejected (attempt {attempt}/{max_attempts}) — concurrent commit from "
              f"another workflow, reloading latest state and retrying...")
        if attempt == max_attempts:
            break

        run(["git", "fetch", "origin", branch])
        run(["git", "reset", "--hard", f"origin/{branch}"])
        time.sleep(delay + random.uniform(0, 1.0))
        delay = min(delay * 1.8, 12.0)

    raise GitSyncError(
        f"git push to {branch} still rejected after {max_attempts} attempts — the repo is under "
        f"heavier concurrent write load than this can absorb. Consider staggering workflow "
        f"schedules further apart."
    )
