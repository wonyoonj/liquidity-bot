# -*- coding: utf-8 -*-
"""
Main script, run once per day (see .github/workflows/daily_post.yml).

CONTENT ROTATION (redesigned):
    Monday    : Weekly Liquidity Result — speedometer gauge + 1W-52W % change
                strip + the top-2 drivers behind this week's number. NO date/
                "updated" text on the card by design (evergreen, not stale-
                looking). Posted once a week only — no repeat daily snapshot.
    Wednesday : Knowledge post — rotates weekly between a liquidity-indicator
                concept (TGA / Fed balance sheet / RRP / bank reserves) and a
                rate concept (Fed Funds / 10Y / 2Y / curve spread / SOFR),
                each shown with a 52-week (or max available) chart and a
                plain-language explainer of how it connects to liquidity.
    Friday    : Term of the Day (finance glossary) — light, distinct content
                that doesn't repeat the liquidity number.
    Sunday    : Community engagement — opinion poll (Telegram native poll +
                Threads open-question mirror).
    Tue/Thu/Sat: No scheduled main post — the urgent scanner below still runs.
    Always    : Unified urgent scanner (lib/signal_scanner.py) — scans EVERY
                monitored series (liquidity + rates + the combined net-flow
                metric) for the single most notable record/streak/turning-
                point/big-move signal, and posts it immediately, independent
                of the weekday schedule above. Posts nothing if nothing is
                genuinely notable that day (quality over forced volume).

POSTING TIMES (see .github/workflows/daily_post.yml for the actual cron):
    Chosen to land within the general "best time to post" window widely
    reported for Western/English-speaking social audiences (mid-morning to
    early afternoon ET on weekdays), spread across Monday / Wednesday /
    Friday / Sunday so the four mandatory posts don't cluster on the same
    day. Cron times are UTC and approximate — they drift by an hour across
    US Daylight Saving transitions; adjust in the workflow file if you want
    to correct for that manually.

Platforms:
    Telegram  : full support (text, photo, native poll)
    Threads   : text-only posts (no native poll support in the API — see
                lib/post_threads.py docstring). Mirrors the same content as
                an open question instead of a poll where applicable.

Local test:
    export TELEGRAM_BOT_TOKEN=xxxx
    export TELEGRAM_CHAT_ID=xxxx
    export FRED_API_KEY=xxxx                # optional
    export THREADS_USER_ID=xxxx             # optional, skip Threads if unset
    export THREADS_ACCESS_TOKEN=xxxx        # optional
    export LLM_PROVIDER=gemini              # or "openai"
    export GEMINI_API_KEY=xxxx              # or OPENAI_API_KEY
    export SITE_URL="https://americayoudongsung.netlify.app/en"   # <-- CONFIRM THIS
    python daily_post.py
"""
from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime, timezone

from lib.fetch_data import fetch_all, FetchError
from lib.compute_liquidity import (
    compute_net_market_flow,
    classify_state,
    compute_net_market_flow_history,
    compute_gauge_angle,
    compute_window_changes,
    compute_top_drivers,
)
from lib.generate_card import (
    create_gauge_card,
    create_knowledge_card,
    create_term_card,
    create_fact_card,
)
from lib.post_telegram import send_photo, send_text, send_poll, TelegramError
from lib.post_threads import publish_text_post, publish_image_post, ThreadsError
from lib.github_image_host import publish_image_to_repo, ImageHostError
from lib.terms import get_term_of_the_day, format_term_caption
from lib.polls import pick_open_question_for_sunday, GENERIC_LIQUIDITY_POLLS
from lib.llm_content import generate_open_question, generate_fact_caption
from lib.reply_templates import generate_reply_snippets, format_reply_toolkit_message
from lib.signal_scanner import get_top_signal
from lib.knowledge_content import build_knowledge_content

# --- IMPORTANT: confirm this matches your actual live English page URL ---
SITE_URL = os.environ.get("SITE_URL", "https://americayoudongsung.netlify.app/en")

MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = range(7)


# ---------------------------------------------------------------------------
# Threads helper — never let a Threads failure break the Telegram post.
# ---------------------------------------------------------------------------
def _mirror_to_threads(text: str, image_path: str | None = None) -> None:
    if not os.environ.get("THREADS_USER_ID") or not os.environ.get("THREADS_ACCESS_TOKEN"):
        print("[Threads] Not configured, skipping mirror post.")
        return

    if image_path:
        try:
            print("[Threads] Publishing generated image to repo for a public URL...")
            image_url = publish_image_to_repo(image_path)
            print(f"  -> {image_url}")
            publish_image_post(text, image_url)
            print("[Threads] Mirrored with image successfully.")
            return
        except (ImageHostError, ThreadsError) as e:
            print(f"[Threads] Image mirror failed, falling back to text-only: {e}", file=sys.stderr)

    try:
        publish_text_post(text)
        print("[Threads] Mirrored (text-only) successfully.")
    except ThreadsError as e:
        print(f"[Threads] Mirror failed (non-fatal): {e}", file=sys.stderr)


def _strip_html(text: str) -> str:
    for tag in ("<b>", "</b>", "<i>", "</i>"):
        text = text.replace(tag, "")
    return text


# ---------------------------------------------------------------------------
# Monday: Weekly Liquidity Result (gauge + % change strip + top drivers)
# ---------------------------------------------------------------------------
def run_monday_liquidity_result(data_store: dict | None = None) -> int:
    print("[1/4] Fetching data...")
    data_store = data_store or fetch_all()

    print("[2/4] Computing this week's liquidity result...")
    result = compute_net_market_flow(data_store)
    state = classify_state(result["net_market_flow"])
    gauge_angle = compute_gauge_angle(result["net_market_flow"])
    window_changes = compute_window_changes(data_store)
    top_drivers = compute_top_drivers(result, top_n=2)
    print(f"  -> {result['net_market_flow']:+.1f} B$/Week — {state['text_en']}")

    print("[3/4] Generating gauge card (no date, auto-cropped)...")
    image_path = create_gauge_card(
        net_market_flow=result["net_market_flow"],
        state=state,
        gauge_angle=gauge_angle,
        window_changes=window_changes,
        top_drivers=top_drivers,
    )

    driver_sentence = " and ".join(
        f"{d['label']} ({'+' if d['value'] > 0 else ''}{d['value']:.1f} B$/Wk)" for d in top_drivers
    )
    sign = "+" if result["net_market_flow"] > 0 else ""
    caption = (
        f"{state['emoji']} <b>US Market Liquidity — Weekly Result</b>\n\n"
        f"Net flow: <b>{sign}{result['net_market_flow']} B$/Week</b> — {state['text_en']}\n\n"
        f"Driven mainly by {driver_sentence}.\n\n"
        f"👉 For full details, check the page: {SITE_URL}\n"
        f"#USLiquidity #FederalReserve"
    )

    print("[4/4] Posting...")
    send_photo(image_path, caption)
    _mirror_to_threads(_strip_html(caption), image_path=image_path)

    print("Done! (Monday liquidity result)")
    return 0


# ---------------------------------------------------------------------------
# Wednesday: Knowledge rotation (liquidity concepts <-> rate concepts)
# ---------------------------------------------------------------------------
def run_wednesday_knowledge(data_store: dict | None = None) -> int:
    print("[1/3] Fetching data...")
    data_store = data_store or fetch_all()

    print("[2/3] Picking this week's knowledge topic...")
    content = build_knowledge_content(data_store)
    if not content:
        print("[WARN] No usable data for this week's topic, skipping gracefully.")
        return 0
    print(f"  -> ({content['pool']}) {content['title']}")

    print("[3/3] Generating chart card + posting...")
    image_path = create_knowledge_card(
        title=content["title"],
        chart_values=content["chart_values"],
        chart_dates=content["chart_dates"],
        unit=content["unit"],
        ticker=content["ticker"],
    )

    caption = (
        f"📚 <b>{content['title']}</b>\n\n"
        f"{content['explainer']}\n\n"
        f"👉 Full charts & data: {SITE_URL}\n"
        f"#USLiquidity #FederalReserve #{content['ticker']}"
    )
    send_photo(image_path, caption)
    _mirror_to_threads(_strip_html(caption), image_path=image_path)

    print("Done! (Wednesday knowledge)")
    return 0


# ---------------------------------------------------------------------------
# Friday: Term of the Day (finance glossary)
# ---------------------------------------------------------------------------
def run_friday_term() -> int:
    print("[1/3] Picking today's term...")
    term_entry = get_term_of_the_day()
    print(f"  -> {term_entry['term']}")

    print("[2/3] Generating term card image...")
    image_path = create_term_card(term_entry["term"], term_entry["definition"])

    print("[3/3] Posting...")
    caption = format_term_caption(term_entry, SITE_URL)
    send_photo(image_path, caption)
    _mirror_to_threads(_strip_html(caption), image_path=image_path)

    print("Done! (Friday term of the day)")
    return 0


# ---------------------------------------------------------------------------
# Sunday: community engagement poll
# ---------------------------------------------------------------------------
def run_sunday_engagement() -> int:
    print("[1/2] Posting opinion poll to Telegram...")
    question = pick_open_question_for_sunday()
    options = next(opts for q, opts in GENERIC_LIQUIDITY_POLLS if q == question)
    send_text(f"💬 <b>This Week's Question</b>\n\n{question}")
    send_poll(question, options)

    print("[2/2] Mirroring to Threads (LLM-phrased open question)...")
    threads_question = generate_open_question("this week's liquidity conditions")
    _mirror_to_threads(threads_question)

    print("Done! (Sunday engagement)")
    return 0


# ---------------------------------------------------------------------------
# Any day: unified urgent scanner (liquidity + rates + combined metric)
# ---------------------------------------------------------------------------
def run_signal_scan(data_store: dict) -> int:
    print("[Signal Scan] Scanning all monitored series for a notable fact...")
    signal = get_top_signal(data_store)
    if not signal:
        print("[Signal Scan] Nothing notable today, skipping.")
        return 0

    print(f"  -> [{signal['category']}] {signal['signal_type']} on {signal['ticker']}: {signal['fact_text']}")

    image_path = create_fact_card(
        fact_text=signal["fact_text"],
        ticker=signal["ticker"],
        chart_values=signal["chart_values"],
        chart_dates=signal["chart_dates"],
        unit=signal["unit"],
    )

    caption = generate_fact_caption(
        fact_text=signal["fact_text"],
        ticker=signal["ticker"],
        current_value=signal["current_value"],
        unit=signal["unit"],
        site_url=SITE_URL,
    )

    send_photo(image_path, caption)
    _mirror_to_threads(_strip_html(caption), image_path=image_path)
    print("[Signal Scan] Posted.")
    return 0


def _send_daily_reply_toolkit(data_store: dict | None = None) -> None:
    """Optional, private, manual-use-only: today's reply snippets for the
    'reply guy' growth strategy. Never posted publicly."""
    try:
        admin_chat_id = os.environ.get("ADMIN_CHAT_ID")
        if not admin_chat_id:
            return
        data_store = data_store or fetch_all()
        result = compute_net_market_flow(data_store)
        snippets = generate_reply_snippets(result, SITE_URL)
        message = format_reply_toolkit_message(snippets, result["as_of_date"])
        send_text(message, chat_id=admin_chat_id)
    except Exception as e:  # noqa: BLE001
        print(f"[Reply Toolkit] Skipped due to error: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
def main() -> int:
    weekday = datetime.now(timezone.utc).weekday()
    rc = 0

    try:
        data_store = fetch_all()

        if weekday == MONDAY:
            rc = run_monday_liquidity_result(data_store)
        elif weekday == WEDNESDAY:
            rc = run_wednesday_knowledge(data_store)
        elif weekday == FRIDAY:
            rc = run_friday_term()
        elif weekday == SUNDAY:
            rc = run_sunday_engagement()
        else:  # Tuesday, Thursday, Saturday — no scheduled main post
            print("No scheduled main post today; running the urgent scanner only.")

        # Unified urgent scanner — runs every day regardless of the branch
        # above, and only posts if something is genuinely notable.
        try:
            run_signal_scan(data_store)
        except Exception as e:  # noqa: BLE001
            print(f"[Signal Scan] Skipped due to error: {e}", file=sys.stderr)

        _send_daily_reply_toolkit(data_store)

        return rc

    except (FetchError, TelegramError, ValueError) as e:
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
        send_text(f"🚨 [Liquidity Bot] Daily post issue\n{message}", chat_id=admin_chat_id)
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())
