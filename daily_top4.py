# -*- coding: utf-8 -*-
"""
Standalone "Daily Top 4 Headlines" script — runs on its OWN schedule (see
.github/workflows/daily_top4.yml), completely separate from daily_post.py's
7-day rotation and from daily_news.py's single-story picker.

Pulls today's (US/Eastern calendar date) headlines from the Reuters
Business & Finance RSS feed (see lib/top4_fetcher.py / lib/news_sources.py's
REUTERS_TOP4_FEED_URL), asks an LLM to pick the 4 most significant, clearly
distinct stories and write a short headline + one-line detail for each (see
lib/llm_content.pick_and_write_top4), renders them onto a numbered-list
summary card (see lib/generate_card.create_top4_card), and posts the result
to Telegram + Threads in this format:

    [Jul 31, 2026] Top News

    1️⃣ HEADLINE ONE
    • Supporting detail.

    2️⃣ HEADLINE TWO
    • Supporting detail.

    3️⃣ HEADLINE THREE
    • Supporting detail.

    4️⃣ HEADLINE FOUR
    • Supporting detail.

    Follow my account to receive the latest updates.

DESIGN — same "no links" approach as daily_news.py: no link to the original
articles, no link to the dashboard site. Attribution is by source name only
("Reuters"), not shown per-item in the card/caption since every item comes
from the same single source this run — do not add per-item source lines or
links without being asked.

If nothing usable comes back today (feed down, LLM unavailable, fewer than
4 distinct stories, or everything found was already covered in the last 45
days), this posts NOTHING — silence is the correct behavior.

Local test:
    export TELEGRAM_BOT_TOKEN=xxxx
    export TELEGRAM_CHAT_ID=xxxx
    export THREADS_USER_ID=xxxx        # optional
    export THREADS_ACCESS_TOKEN=xxxx   # optional
    export LLM_PROVIDER=gemini         # or "openai" — REQUIRED for this feature
    export GEMINI_API_KEY=xxxx         # or OPENAI_API_KEY
    python daily_top4.py
"""
from __future__ import annotations

import os
import sys
import traceback

from lib.top4_fetcher import fetch_today_entries, us_today_label
from lib.top4_state import load_posted_ids, record_posted_many
from lib.llm_content import pick_and_write_top4
from lib.generate_card import create_top4_card
from lib.post_telegram import send_photo, send_text, TelegramError
from lib.post_threads import publish_text_post, publish_image_post, reply_to_post, ThreadsError
from lib.github_image_host import publish_image_to_repo, ImageHostError
from lib.text_split import split_text_by_length, THREADS_CHAR_LIMIT

NUMBER_EMOJI = ["1\ufe0f\u20e3", "2\ufe0f\u20e3", "3\ufe0f\u20e3", "4\ufe0f\u20e3"]  # 1️⃣ 2️⃣ 3️⃣ 4️⃣


def _build_caption(items: list[dict], date_label: str) -> str:
    lines = [f"[{date_label}] Top News", ""]
    for emoji, item in zip(NUMBER_EMOJI, items):
        lines.append(f"{emoji} {item['headline'].upper()}")
        lines.append(f"\u2022 {item['bullet']}")
        lines.append("")
    lines.append("Follow my account to receive the latest updates.")
    return "\n".join(lines)


def _mirror_to_threads_no_link(caption: str, image_path: str | None) -> None:
    """Same chained-reply-on-overflow pattern as daily_news.py's
    _mirror_to_threads_no_link — this feature also carries zero links."""
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
        print("[1/4] Fetching today's Reuters Business & Finance headlines...")
        candidates = fetch_today_entries()
        print(f"  -> {len(candidates)} candidate entries fetched")

        already_posted = load_posted_ids()
        fresh = [c for c in candidates if c["id"] not in already_posted]
        print(f"  -> {len(fresh)} remaining after removing already-covered stories")

        if not fresh:
            print("No fresh candidates today — skipping silently "
                  "(this is expected behavior, not an error).")
            return 0

        # Post with as many distinct stories as are actually available today,
        # up to 4 — 2 or 3 solid, genuinely distinct items is a perfectly
        # fine post; we never pad the list by inventing or repeating a story
        # just to reach 4.
        target_count = min(len(fresh), 4)

        # Cap the shortlist sent to the LLM — keeps the prompt small/cheap.
        shortlist = fresh[:20]

        print(f"[2/4] Asking the LLM to pick + write the top {target_count} headline(s)...")
        items = pick_and_write_top4(shortlist, count=target_count)
        if not items:
            print("LLM did not return any usable items today — skipping silently.")
            return 0
        if len(items) < target_count:
            print(f"  -> only {len(items)} distinct, usable item(s) came back "
                  f"(asked for {target_count}) — posting with what's available.")
        for i, it in enumerate(items, start=1):
            print(f"  -> {i}. {it['headline']}")

        date_label = us_today_label()

        print("[3/4] Generating the Top 4 summary card...")
        card_path = create_top4_card(items, date_label=date_label)

        print("[4/4] Posting (no links — Reuters attribution only)...")
        caption = _build_caption(items, date_label)
        telegram_caption = caption + "\n\n<i>Source: Reuters Business &amp; Finance</i>"
        send_photo(card_path, telegram_caption)
        _mirror_to_threads_no_link(caption, card_path)

        record_posted_many([(it["id"], it["title"]) for it in items])
        print("Done! (daily top 4 headlines)")
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
        send_text(f"\U0001f6a8 [Liquidity Bot — Top4] Daily top-4 headlines post issue\n{message}", chat_id=admin_chat_id)
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())
