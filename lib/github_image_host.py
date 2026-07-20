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
"""
from __future__ import annotations

import os
import time
import shutil
import subprocess
from datetime import datetime, timezone

import requests


class ImageHostError(RuntimeError):
    pass


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(f"    $ {' '.join(cmd)}")
    if result.stdout.strip():
        print(f"      stdout: {result.stdout.strip()}")
    if result.stderr.strip():
        print(f"      stderr: {result.stderr.strip()}")
    if check and result.returncode != 0:
        raise ImageHostError(f"Command failed ({result.returncode}): {' '.join(cmd)}\n{result.stderr}")
    return result


def _wait_until_reachable(url: str, max_attempts: int = 10, base_delay: float = 3.0) -> None:
    """Polls the URL with exponential backoff. Raises only after genuinely
    exhausting the window — worst case ~2 minutes, comfortably covering
    normal raw.githubusercontent.com CDN propagation delay."""
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
            delay = min(delay * 1.6, 30.0)  # cap individual waits at 30s

    raise ImageHostError(
        f"Image URL never became reachable after {max_attempts} attempts (last: {last_status}): {url}"
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

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    ext = os.path.splitext(local_path)[1] or ".png"
    dest_rel_path = f"{folder}/{ts}{ext}"

    print(f"[github_image_host] Copying {local_path} -> {dest_rel_path}")
    os.makedirs(folder, exist_ok=True)
    shutil.copyfile(local_path, dest_rel_path)

    _run(["git", "config", "user.name", "liquidity-bot"])
    _run(["git", "config", "user.email", "liquidity-bot@users.noreply.github.com"])
    _run(["git", "add", dest_rel_path])

    diff_check = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if diff_check.returncode == 0:
        raise ImageHostError(f"Nothing to commit — {dest_rel_path} is identical to an existing file?")

    print("[github_image_host] Committing...")
    _run(["git", "commit", "-m", f"chore: add {dest_rel_path} [skip ci]"])

    print("[github_image_host] Pushing...")
    push_result = _run(["git", "push", "origin", f"HEAD:{branch}"], check=False)
    if push_result.returncode != 0:
        raise ImageHostError(
            f"git push FAILED (exit {push_result.returncode}) — this is a real push failure, "
            f"not a CDN delay. Check branch protection rules / token permissions.\n{push_result.stderr}"
        )

    local_head = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
    print(f"[github_image_host] Pushed commit {local_head[:10]} to {branch}. Verifying public URL...")

    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{dest_rel_path}"
    _wait_until_reachable(url)
    return url
