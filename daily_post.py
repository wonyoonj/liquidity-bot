# -*- coding: utf-8 -*-
"""
Main script, run once per day (see .github/workflows/daily_post.yml).

Content rotation:
    Monday    : Weekly economic calendar (FRED) + Telegram poll tied to the
                biggest event this week + Threads open-question post
    Tue-Thu   : Daily snapshot card + LLM-generated "angle" commentary
    Friday    : Weekly recap chart
    Saturday  : Term of the Day (finance glossary)
    Sunday    : Story/record recap + opinion poll (idea #10)
    Always    : Event triggers (streak / record / turning point) checked on
                every run and posted immediately if fired, regardless of weekday.

Platforms:
    Telegram  : full support (text, photo, native poll)
    Threads   : text-only posts (no native poll support in the API — see
                lib/post_threads.py docstring). Mirrors the same content as
                an open question instead of a poll where applicable.

Local test:
    export TELEGRAM_BOT_TOKEN=xxxx
    export TELEGRAM_CHAT_ID=xxxx
    export FRED_API_KEY=xxxx                # optional, Monday calendar
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
    compute_trend_text,
    compute_net_market_flow_history,
)
from lib.generate_card import create_summary_card, create_weekly_recap_card
from lib.post_telegram import send_photo, send_text, send_poll, TelegramError
from lib.post_threads import publish_text_post, publish_image_post, ThreadsError
from lib.github_image_host import publish_image_to_repo, ImageHostError
from lib.fetch_calendar import get_upcoming_releases, format_weekly_calendar_caption, CalendarError
from lib.terms import get_term_of_the_day, format_term_caption
from lib.story import build_story_caption, _current_streak
from lib.triggers import check_triggers
from lib.polls import pick_poll_for_week, pick_open_question_for_sunday
from lib.llm_content import generate_angle_commentary, generate_open_question
from lib.reply_templates import generate_reply_snippets, format_reply_toolkit_message

# --- IMPORTANT: confirm this matches your actual live English page URL ---
SITE_URL = os.environ.get("SITE_URL", "https://americayoudongsung.netlify.app/en")

MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = range(7)


# ---------------------------------------------------------------------------
# Threads helper — never let a Threads failure break the Telegram post.
# Threads credentials are optional; if not configured, this silently skips.
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
            # fall through to text-only below

    try:
        publish_text_post(text)
        print("[Threads] Mirrored (text-only) successfully.")
    except ThreadsError as e:
        print(f"[Threads] Mirror failed (non-fatal): {e}", file=sys.stderr)


def _strip_html(text: str) -> str:
    """Threads posts are plain text; Telegram captions use light HTML. Strip <b> tags etc."""
    for tag in ("<b>", "</b>", "<i>", "</i>"):
        text = text.replace(tag, "")
    return text


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _biggest_driver_label(result: dict) -> str:
    contributions = {
        "the Treasury's TGA balance": -result["tga_diff"],
        "the Fed's balance sheet / reserves": result["fed_liquidity_diff"],
        "Money Market Fund flows": result["final_mmf_to_market_diff"],
    }
    return max(contributions, key=lambda k: abs(contributions[k]))


def _build_llm_metrics(data_store: dict, result: dict, window_weeks: int = 12) -> dict:
    history = compute_net_market_flow_history(data_store, weeks=window_weeks)
    values = [h["net_market_flow"] for h in history]
    if not values:
        return {"net_market_flow": result["net_market_flow"], "as_of_date": result["as_of_date"]}

    avg = sum(values) / len(values)
    rank_desc = sorted(values, reverse=True)
    rank_asc = sorted(values)
    current_val = values[-1]
    streak = _current_streak(values)

    return {
        "net_market_flow": result["net_market_flow"],
        "as_of_date": result["as_of_date"],
        "window_weeks": window_weeks,
        "avg": round(avg, 1),
        "supply_rank": rank_desc.index(current_val) + 1,
        "drain_rank": rank_asc.index(current_val) + 1,
        "n_weeks": len(values),
        "streak_length": streak["length"],
        "streak_direction": "supply" if streak["direction"] > 0 else "drain",
        "biggest_driver": _biggest_driver_label(result),
    }


def _run_triggers_if_any(data_store: dict) -> None:
    """Idea #3 / #6: fire an immediate extra post if something noteworthy
    happened, independent of which day's scheduled content already ran."""
    try:
        history = compute_net_market_flow_history(data_store, weeks=52)
        alerts = check_triggers(history)
        for alert in alerts:
            print(f"[Trigger] Firing: {alert[:60]}...")
            send_text(alert)
            _mirror_to_threads(_strip_html(alert))
    except Exception as e:  # noqa: BLE001
        # Triggers are a bonus feature; never let them break the main post.
        print(f"[Trigger] Skipped due to error: {e}", file=sys.stderr)


def _send_daily_reply_toolkit(data_store: dict | None = None) -> None:
    """Sends a private message (to ADMIN_CHAT_ID only) with a handful of
    copy-paste-ready reply snippets for the 'reply guy' growth strategy —
    see lib/reply_templates.py. Never auto-posted anywhere; purely a manual
    tool. Silently skipped if ADMIN_CHAT_ID isn't configured, and never lets
    a failure here break the rest of the run."""
    admin_chat_id = os.environ.get("ADMIN_CHAT_ID")
    if not admin_chat_id:
        return
    try:
        data_store = data_store or fetch_all()
        result = compute_net_market_flow(data_store)
        state = classify_state(result["net_market_flow"])
        metrics = {"net_market_flow": result["net_market_flow"], "state_label": state["text_en"]}
        snippets = generate_reply_snippets(metrics, SITE_URL)
        message = format_reply_toolkit_message(snippets, result["as_of_date"])
        send_text(message, chat_id=admin_chat_id)
        print("[Reply Toolkit] Sent to admin chat.")
    except Exception as e:  # noqa: BLE001
        print(f"[Reply Toolkit] Skipped due to error: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Tuesday - Thursday: daily snapshot + LLM angle commentary
# ---------------------------------------------------------------------------
def run_daily_snapshot(data_store: dict | None = None) -> int:
    print("[1/5] Fetching data...")
    data_store = data_store or fetch_all()

    print("[2/5] Computing liquidity metrics...")
    result = compute_net_market_flow(data_store)
    state = classify_state(result["net_market_flow"])
    trend_text = compute_trend_text(data_store, result)
    print(f"  -> {result}")

    print("[3/5] Generating LLM angle commentary...")
    llm_metrics = _build_llm_metrics(data_store, result)
    angle_line = generate_angle_commentary(llm_metrics)
    print(f"  -> {angle_line}")

    print("[4/5] Generating card image...")
    image_path = create_summary_card(
        net_market_flow=result["net_market_flow"],
        state=state,
        as_of_date=result["as_of_date"],
        trend_text=trend_text,
    )

    print("[5/5] Posting...")
    sign = "+" if result["net_market_flow"] > 0 else ""
    caption = (
        f"{state['emoji']} <b>US Market Liquidity Update</b> (as of {result['as_of_date']})\n\n"
        f"Market Total Net Liquidity Supply: <b>{sign}{result['net_market_flow']} B$/Week</b>\n"
        f"Status: <b>{state['text_en']}</b>{trend_text}\n\n"
        f"{angle_line}\n\n"
        f"👉 {SITE_URL}\n"
        f"#USLiquidity #FederalReserve #TGA #ReverseRepo"
    )
    send_photo(image_path, caption)
    _mirror_to_threads(_strip_html(
        f"{state['emoji']} US Market Liquidity Update ({result['as_of_date']})\n\n"
        f"Net flow: {sign}{result['net_market_flow']} B$/Week — {state['text_en']}\n\n"
        f"{angle_line}\n\n{SITE_URL}"
    ), image_path=image_path)

    _run_triggers_if_any(data_store)
    print("Done! (daily snapshot)")
    return 0


# ---------------------------------------------------------------------------
# Monday: economic calendar + poll tied to this week's biggest event
# ---------------------------------------------------------------------------
def run_monday_calendar() -> int:
    print("[1/3] Fetching FRED release calendar...")
    events = get_upcoming_releases(days_ahead=7)
    print(f"  -> {events}")

    print("[2/3] Posting calendar + poll to Telegram...")
    caption = format_weekly_calendar_caption(events, SITE_URL)
    send_text(caption)

    question, options = pick_poll_for_week(events)
    send_poll(question, options)

    print("[3/3] Mirroring to Threads (text + open question, no native poll)...")
    threads_text = _strip_html(caption) + f"\n\nThis week's question: {question}\n(Reply with your take!)"
    _mirror_to_threads(threads_text)

    print("Done! (weekly calendar + poll)")
    return 0


# ---------------------------------------------------------------------------
# Friday: weekly recap chart
# ---------------------------------------------------------------------------
def run_friday_recap(data_store: dict | None = None) -> int:
    print("[1/3] Fetching data...")
    data_store = data_store or fetch_all()

    print("[2/3] Building weekly history + recap chart...")
    history = compute_net_market_flow_history(data_store, weeks=8)
    image_path = create_weekly_recap_card(history)
    print(f"  -> {len(history)} weeks, {image_path}")

    print("[3/3] Posting...")
    if history:
        latest = history[-1]["net_market_flow"]
        avg = sum(h["net_market_flow"] for h in history) / len(history)
        caption = (
            f"📊 <b>Weekly Recap — Net Liquidity Flow</b>\n\n"
            f"This week: <b>{latest:+.1f} B$/Week</b>   ·   "
            f"{len(history)}-week average: <b>{avg:+.1f} B$/Week</b>\n\n"
            f"👉 {SITE_URL}\n"
            f"#USLiquidity #WeeklyRecap #FederalReserve"
        )
    else:
        caption = f"📊 <b>Weekly Recap</b>\n\nNot enough data this week.\n\n👉 {SITE_URL}"
    send_photo(image_path, caption)
    _mirror_to_threads(_strip_html(caption), image_path=image_path)

    _run_triggers_if_any(data_store)
    print("Done! (Friday recap)")
    return 0


# ---------------------------------------------------------------------------
# Saturday: term of the day
# ---------------------------------------------------------------------------
def run_saturday_term() -> int:
    print("[1/2] Picking today's term...")
    term_entry = get_term_of_the_day()
    print(f"  -> {term_entry['term']}")

    print("[2/2] Posting...")
    caption = format_term_caption(term_entry, SITE_URL)
    send_text(caption)
    _mirror_to_threads(_strip_html(caption))

    print("Done! (term of the day)")
    return 0


# ---------------------------------------------------------------------------
# Sunday: story/record recap + opinion poll (idea #10)
# ---------------------------------------------------------------------------
def run_sunday_story(data_store: dict | None = None) -> int:
    print("[1/3] Fetching data + building history...")
    data_store = data_store or fetch_all()
    history = compute_net_market_flow_history(data_store, weeks=52)
    print(f"  -> {len(history)} weeks of history")

    print("[2/3] Posting story + poll to Telegram...")
    caption = build_story_caption(history, SITE_URL)
    send_text(caption)

    question = pick_open_question_for_sunday()
    send_poll(question, ["Yes, clearly", "Somewhat", "No, not really", "Not sure"])

    print("[3/3] Mirroring to Threads (open question, LLM-phrased)...")
    threads_question = generate_open_question("this week's net liquidity flow", context_note=caption[:300])
    _mirror_to_threads(_strip_html(caption) + f"\n\n{threads_question}")

    _run_triggers_if_any(data_store)
    print("Done! (Sunday story)")
    return 0


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
def main() -> int:
    weekday = datetime.now(timezone.utc).weekday()
    rc = 1

    try:
        if weekday == MONDAY:
            try:
                rc = run_monday_calendar()
            except CalendarError as e:
                print(f"[WARN] Calendar content failed, falling back to snapshot: {e}", file=sys.stderr)
                _notify_admin_on_error(f"[Monday calendar failed, fell back to snapshot] {e}")
                rc = run_daily_snapshot()

        elif weekday == FRIDAY:
            rc = run_friday_recap()

        elif weekday == SATURDAY:
            rc = run_saturday_term()

        elif weekday == SUNDAY:
            rc = run_sunday_story()

        else:  # Tuesday, Wednesday, Thursday
            rc = run_daily_snapshot()

        # Optional, private, manual-use-only: today's reply snippets for the
        # "reply guy" growth strategy (see lib/reply_templates.py). Never
        # posted publicly, and never allowed to affect the return code.
        _send_daily_reply_toolkit()

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
