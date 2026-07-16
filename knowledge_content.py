# -*- coding: utf-8 -*-
"""
Threads image posts require a PUBLICLY reachable image_url (Threads fetches
it server-side; you can't upload raw bytes). Solution: commit the generated
PNG straight into this GitHub repo during the Actions run, then build a
raw.githubusercontent.com URL pointing at it. Free, no extra service needed.

Requires the workflow to have `permissions: contents: write` and either the
default GITHUB_TOKEN or GH_PAT for pushing (see .github/workflows/daily_post.yml).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone


class ImageHostError(RuntimeError):
    pass


def _run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise ImageHostError(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout.strip()


def publish_image_to_repo(local_path: str, folder: str = "images") -> str:
    """Copies local_path into <repo>/<folder>/, commits, and pushes it.
    Returns the public raw.githubusercontent.com URL for the committed file.
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

    return f"https://raw.githubusercontent.com/{repo}/{branch}/{dest_rel_path}"
