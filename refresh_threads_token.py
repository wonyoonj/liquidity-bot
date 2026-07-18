# -*- coding: utf-8 -*-
"""
Refreshes the Threads long-lived access token BEFORE it expires (Meta tokens
last 60 days) and writes the new token back into GitHub Secrets automatically
— so a human never has to re-run the OAuth flow manually.

Run on its own schedule (weekly is plenty; see
.github/workflows/refresh_threads_token.yml), separate from the daily post
workflow, to keep concerns isolated.

Requires:
    THREADS_ACCESS_TOKEN  (current token, as a GitHub Secret)
    GH_PAT                (Personal Access Token with repo secrets write access)
    GH_REPO                "owner/repo"
    ADMIN_CHAT_ID / TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (optional, for failure alerts)
"""
from __future__ import annotations

import os
import sys

from lib.post_threads import refresh_long_lived_token, ThreadsError
from lib.github_secrets import update_repo_secret, GitHubSecretError
from lib.post_telegram import send_text, TelegramError


def main() -> int:
    current_token = os.environ.get("THREADS_ACCESS_TOKEN")
    if not current_token:
        print("[SKIP] THREADS_ACCESS_TOKEN not set — Threads isn't configured, nothing to refresh.")
        return 0

    try:
        print("[1/2] Refreshing Threads access token...")
        data = refresh_long_lived_token(current_token)
        new_token = data["access_token"]
        expires_in_days = round(data.get("expires_in", 0) / 86400, 1)
        print(f"  -> new token valid for ~{expires_in_days} more days")

        print("[2/2] Writing new token back to GitHub Secrets...")
        update_repo_secret("THREADS_ACCESS_TOKEN", new_token)
        print("Done! Token refreshed and stored — no manual action needed.")
        return 0

    except (ThreadsError, GitHubSecretError) as e:
        print(f"[ERROR] Token refresh failed: {e}", file=sys.stderr)
        _notify_admin(f"🚨 Threads token refresh FAILED — manual re-auth may be needed soon.\n{e}")
        return 1


def _notify_admin(message: str) -> None:
    admin_chat_id = os.environ.get("ADMIN_CHAT_ID")
    if not admin_chat_id:
        return
    try:
        send_text(message, chat_id=admin_chat_id)
    except TelegramError:
        pass


if __name__ == "__main__":
    sys.exit(main())
