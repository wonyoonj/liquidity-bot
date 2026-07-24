# -*- coding: utf-8 -*-
"""
Standalone daily news script — runs on its OWN schedule (see
.github/workflows/daily_news.yml), completely separate from daily_post.py's
7-day content rotation. Picks the single most US-dollar-liquidity-relevant
news story from the last ~30 hours across the sources in
lib/news_sources.py, and posts a short paraphrased summary + a plain
expected-impact line.

DESIGN — per explicit instruction, this feature carries NO links at all:
    - no link to the original article (attribution is by SOURCE NAME only,
      shown on the card and in the caption footer)
    - no link to the dashboard site either
This is intentionally different from daily_post.py's posts, which do link to
the site. Do not add a site link here without being asked.

If nothing new/relevant is found (either no qualifying news today, or
everything found was already covered in the last 45 days), this posts
NOTHING — silence is the correct behavior, not a forced filler post.

Local test:
    export TELEGRAM_BOT_TOKEN=xxxx
    export TELEGRAM_CHAT_ID=xxxx
    export THREADS_USER_ID=xxxx        # optional
    export THREADS_ACCESS_TOKEN=xxxx   # optional
    export LLM_PROVIDER=gemini         # or "openai" — REQUIRED for this feature
    export GEMINI_API_KEY=xxxx         # or OPENAI_API_KEY
    python daily_news.py
"""
from __future__ import annotations

import os
import sys
import traceback

from lib.news_scanner import get_daily_news_pick, mark_news_posted
from lib.generate_card import create_news_card
from lib.news_image import download_image, fetch_og_image
from lib.post_telegram import send_photo, send_text, TelegramError
from lib.post_threads import publish_text_post, publish_image_post, reply_to_post, ThreadsError
from lib.github_image_host import publish_image_to_repo, ImageHostError
from lib.text_split import split_text_by_length, THREADS_CHAR_LIMIT


def _mirror_to_threads_no_link(caption: str, image_path: str | None) -> None:
    """Minimal Threads mirror for this feature only — deliberately does NOT
    use daily_post.py's _mirror_to_threads (which posts the site link as a
    reply), because news posts must carry zero links of any kind.

    v2: splits overflow into chained replies (same fix as daily_post.py's
    _mirror_to_threads) instead of relying on post_threads.py's safety-net
    truncation."""
    if not os.environ.get("THREADS_USER_ID") or not os.environ.get("THREADS_ACCESS_TOKEN"):
        print("[Threads] Not configured, skipping mirror post.")
        return
    chunks = split_text_by_length(caption, THREADS_CHAR_LIMIT) or [""]
    first_chunk, overflow_chunks = chunks[0], chunks[1:]
    try:
        if image_path:
            image_url = publish_image_to_repo(image_path)
            resp = publish_image_post(first_chunk, image_url)
        else:
            resp = publish_text_post(first_chunk)
        print("[Threads] Mirrored successfully.")
        last_id = resp.get("id")
        for chunk in overflow_chunks:
            if not last_id:
                break
            reply = reply_to_post(last_id, chunk)
            last_id = reply.get("id") or last_id
            print("[Threads] Continuation posted as a reply.")
    except (ImageHostError, ThreadsError) as e:
        print(f"[Threads] Mirror failed (non-fatal): {e}", file=sys.stderr)


def main() -> int:
    try:
        print("[1/3] Scanning RSS sources for today's most liquidity-relevant story...")
        pick = get_daily_news_pick()
        if not pick:
            print("Nothing new/relevant to post today — skipping silently (this is expected behavior).")
            return 0

        print("[2/3] Fetching the story's photo (RSS thumbnail, else og:image)...")
        photo_path = None
        if pick.get("image_url"):
            photo_path = download_image(pick["image_url"], "output/news_photo.jpg")
        if not photo_path:
            og_url = fetch_og_image(pick.get("_article_link") or "")
            if og_url:
                photo_path = download_image(og_url, "output/news_photo.jpg")
        if photo_path:
            print(f"  -> using photo: {photo_path}")
        else:
            print("  -> no usable photo found, card will use the placeholder panel")

        print("[3/3] Generating the news card (headline + photo only)...")
        card_path = create_news_card(
            headline=pick["headline"],
            source_name=pick["source_name"],
            photo_path=photo_path,
        )

        print("Posting (no links — source-name attribution only)...")
        caption = (
            f"📰 <b>{pick['headline']}</b>\n\n"
            f"{pick['summary']}\n\n"
            f"<i>Expected impact:</i> {pick['impact']}\n\n"
            f"Source: {pick['source_name']}"
        )
        send_photo(card_path, caption)

        plain_caption = (
            f"📰 {pick['headline']}\n\n"
            f"{pick['summary']}\n\n"
            f"Expected impact: {pick['impact']}\n\n"
            f"Source: {pick['source_name']}"
        )
        _mirror_to_threads_no_link(plain_caption, card_path)

        mark_news_posted(pick)
        print("Done! (daily news pick)")
        return 0

    except (TelegramError, ValueError) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        _notify_admin_on_error(str(e))
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"[UNEXPECTED ERROR] {e}", file=sys.stderr)
        traceback.print_exc()
        _notify_admin_on_error(f"Unexpected error: {e}")
        return 1


def _notify_admin_on_error(message: str) -> None:
    admin_chat_id = os.environ.get("ADMIN_CHAT_ID")
    if not admin_chat_id:
        return
    try:
        send_text(f"🚨 [Liquidity Bot — News] Daily news post issue\n{message}", chat_id=admin_chat_id)
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())
