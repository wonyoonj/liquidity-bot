# -*- coding: utf-8 -*-
"""
Threads image posts require a PUBLICLY reachable image_url (Threads fetches
it server-side; you can't upload raw bytes). Solution: commit the generated
PNG straight into this GitHub repo during the Actions run, then build a
raw.githubusercontent.com URL pointing at it. Free, no extra service needed.

Requires the workflow to have `permissions: contents: write` and either the
default GITHUB_TOKEN or GH_PAT for pushing (see .github/workflows/daily_post.yml).

RELIABILITY FIX (July 2026): raw.githubusercontent.com can take a few
seconds to serve a just-pushed file. Previously we returned the URL
immediately, so Threads sometimes tried to fetch it before it was live and
the image post silently failed → fell back to text-only (this was the
missing-image bug on Threads). Now we poll the URL with retries before
returning it, and raise ImageHostError only if it never becomes reachable.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from datetime import datetime, timezone

import requests


class ImageHostError(RuntimeError):
    pass


def _run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise ImageHostError(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout.strip()


def _wait_until_live(url: str, attempts: int = 6, delay_seconds: float = 2.0) -> None:
    """Polls the raw URL with a HEAD request until it returns 200, so the
    caller never hands Threads a URL that isn't actually servable yet."""
    last_status = None
    for _ in range(attempts):
        try:
            resp = requests.head(url, timeout=10, allow_redirects=True)
            last_status = resp.status_code
            if resp.status_code == 200:
                return
        except requests.RequestException as e:
            last_status = str(e)
        time.sleep(delay_seconds)
    raise ImageHostError(f"Image URL never became reachable after {attempts} attempts (last: {last_status}): {url}")


def publish_image_to_repo(local_path: str, folder: str = "images") -> str:
    """Copies local_path into <repo>/<folder>/, commits, and pushes it.
    Returns the public raw.githubusercontent.com URL for the committed file,
    only after confirming it's actually reachable (see _wait_until_live).
    Uses a date+time-based filename so every post gets its own permanent URL
    (avoids any CDN caching issues from overwriting the same filename)."""
    repo = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        raise ImageHostError("GH_REPO / GITHUB_REPOSITORY is not set — can't build a public URL.")

    branch = os.environ.get("GH_BRANCH", "main")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    ext = os.path.splitext(local_path)[1] or ".png"
    dest_rel_path = f"{folder}/{ts}{ext}"

    os.makedirs(folder, exist_ok=True)
    shutil.copyfile(local_path, dest_rel_path)

    _run(["git", "config", "user.name", "liquidity-bot"])
    _run(["git", "config", "user.email", "liquidity-bot@users.noreply.github.com"])
    _run(["git", "add", dest_rel_path])

    diff_check = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if diff_check.returncode == 0:
        raise ImageHostError("Nothing to commit (file identical to an existing one?).")

    _run(["git", "commit", "-m", f"chore: add {dest_rel_path} [skip ci]"])
    _run(["git", "push", "origin", f"HEAD:{branch}"])

    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{dest_rel_path}"
    _wait_until_live(url)
    return url
