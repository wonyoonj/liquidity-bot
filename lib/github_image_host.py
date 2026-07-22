# -*- coding: utf-8 -*-
"""
Commits a generated card image into the repo and returns its public
raw.githubusercontent.com URL, for Threads image posts (Threads requires a
publicly reachable URL — it can't accept uploaded bytes directly).

v2: fixes a real production bug where every image mirror was silently
falling back to text-only. Root cause was ambiguous before this version:
raw.githubusercontent.com is served through a CDN, and a just-pushed file
can take anywhere from a few seconds to (rarely) over a minute to become
fetchable — the previous retry window wasn't long enough to reliably absorb
that delay, AND git push success/failure was never actually logged, so it
was impossible to tell "push failed" apart from "push worked, CDN is just
slow" from the Action logs alone. Both are fixed here:
    1. git add/commit/push output is now always printed, so a real push
       failure (auth, branch protection, etc.) shows up immediately and
       distinctly from a slow-CDN 404.
    2. The reachability poll now waits much longer with exponential backoff
       before giving up (worst case ~2 minutes total), which comfortably
       covers normal CDN propagation delay.

v3 (this version): fixes the *next* failure mode, seen after v2 —
`git push` itself getting rejected with "! [rejected] HEAD -> main (fetch
first)". That happens when another workflow run (daily_news.py,
refresh_threads_token.py, or a second image in the same daily_post.py run)
commits to the repo in between. Pushing is now retried via
lib/git_sync.push_with_retry, which fetches + rebases onto the new remote
tip and tries again instead of failing immediately. Also gives each image
filename microsecond precision so two images published within the same
run/second never collide on `dest_rel_path`.
"""
from __future__ import annotations

import os
import time
import shutil
import subprocess
from datetime import datetime, timezone

import requests

from lib.git_sync import run as _run, configure_identity, push_with_retry, GitSyncError


class ImageHostError(RuntimeError):
    pass


def _wait_until_reachable(url: str, max_attempts: int = 6, base_delay: float = 3.0) -> None:
    """Polls the URL with exponential backoff. Raises only after genuinely
    exhausting the window (~50s total) — a real CDN propagation delay always
    resolves within seconds, so there's no point waiting minutes for it.

    v3 note: if this still 404s after several attempts AND the git push
    above clearly succeeded, it is almost never a propagation delay — it is
    almost always because the repo is PRIVATE. raw.githubusercontent.com
    returns 404 (not 403) for private-repo content specifically so it can't
    be used to probe whether a private repo exists, and there's no way for
    an external service like Threads to authenticate to fetch it. Waiting
    longer will never fix this — the fix is making the repo public (GitHub
    Secrets stay encrypted and protected regardless of repo visibility, so
    this doesn't expose your tokens/keys)."""
    delay = base_delay
    last_status = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.head(url, timeout=10, allow_redirects=True)
            last_status = resp.status_code
            if resp.status_code == 200:
                print(f"    reachable after {attempt} attempt(s)")
                return
        except requests.RequestException as e:
            last_status = f"exception: {e}"

        if attempt < max_attempts:
            time.sleep(delay)
            delay = min(delay * 1.6, 15.0)

    hint = (
        " <- if the git push above succeeded and this is STILL 404 after "
        "multiple attempts, your repo is almost certainly PRIVATE. "
        "raw.githubusercontent.com cannot serve private-repo files to an "
        "external service like Threads. Fix: Settings -> General -> Danger "
        "Zone -> Change visibility -> Public (your Secrets remain fully "
        "protected either way)."
        if last_status == 404 else ""
    )
    raise ImageHostError(
        f"Image URL never became reachable after {max_attempts} attempts (last: {last_status}): {url}{hint}"
    )


def publish_image_to_repo(local_path: str, folder: str = "images") -> str:
    """Copies local_path into <repo>/<folder>/, commits, pushes, VERIFIES the
    push actually landed (checks the real exit code, not just assumes),
    then polls the public URL until it's genuinely fetchable. Raises
    ImageHostError with a clear, specific reason on any failure — callers
    should catch this and fall back to a text-only post."""
    repo = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        raise ImageHostError("GH_REPO / GITHUB_REPOSITORY is not set — can't build a public URL.")
    branch = os.environ.get("GH_BRANCH", "main")

    # Microsecond precision (not just seconds) so two images published in the
    # same run — e.g. daily_post.py's calendar card + signal card — never
    # collide on dest_rel_path and get mistaken for "nothing to commit".
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    ext = os.path.splitext(local_path)[1] or ".png"
    dest_rel_path = f"{folder}/{ts}{ext}"

    print(f"[github_image_host] Copying {local_path} -> {dest_rel_path}")
    os.makedirs(folder, exist_ok=True)
    shutil.copyfile(local_path, dest_rel_path)

    configure_identity()
    _run(["git", "add", dest_rel_path])

    diff_check = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if diff_check.returncode == 0:
        raise ImageHostError(f"Nothing to commit — {dest_rel_path} is identical to an existing file?")

    print("[github_image_host] Committing...")
    _run(["git", "commit", "-m", f"chore: add {dest_rel_path} [skip ci]"])

    print("[github_image_host] Pushing (with retry on concurrent-write conflicts)...")
    try:
        push_with_retry(branch)
    except GitSyncError as e:
        raise ImageHostError(str(e)) from e

    local_head = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
    print(f"[github_image_host] Pushed commit {local_head[:10]} to {branch}. Verifying public URL...")

    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{dest_rel_path}"
    _wait_until_reachable(url)
    return url
