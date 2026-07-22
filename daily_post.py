# -*- coding: utf-8 -*-
"""
Main script, run once per day (see .github/workflows/daily_post.yml).

CONTENT ROTATION:
    Monday    : Weekly Liquidity Index — TWO images: (1) the site's actual
                percentile-based gauge (dome-up speedometer, 0=UNDERSUPPLY,
                100=FLOODED) + top-2 drivers, and (2) a 52-week trend chart
                of the underlying NETMARKETFLOW figure. NO date/"updated"
                text on the gauge card by design (evergreen, not stale-
                looking). Posted once a week only — no repeat daily snapshot.
    Tuesday   : This month's econ calendar — a calendar IMAGE (all events,
                past ones checked off) + a caption listing the top-3 most
                important upcoming releases with an LLM-written explanation
                of why the single most important one matters.
    Wednesday
    & Thursday: IDENTICAL routine (same function, same chart style, same
                posting time) — a knowledge post rotating weekly between a
                liquidity-indicator concept and a rate concept, each with a
                52-week chart card and an LLM "why it matters" line.
    Friday    : Term of the Day — an illustrated card (text monogram badge,
                since the bundled font has no emoji glyphs) with an LLM
                "why it matters" line.
    Sunday    : Community engagement — native poll on both Telegram and
                Threads (Threads added poll_attachment support April 2025).
    Saturday  : No scheduled main post — the urgent scanner below still runs.
    Always    : Unified urgent scanner (lib/signal_scanner.py) — scans EVERY
                monitored series (liquidity + rates + the combined net-flow
                metric) for the single most notable record/streak/turning-
                point/big-move signal, posts it with an LLM "why it matters"
                line, independent of the weekday schedule above. Posts
                nothing if nothing is genuinely notable that day.

EXPOSURE-STRATEGY FIXES APPLIED (see README for the full write-up):
    1. NO HASHTAGS anywhere, on either platform.
    2. Every scheduled post now ALWAYS carries an image (previously Tuesday/
       Friday were text-only). The Threads image-hosting reliability bug
       (image silently failing -> falling back to text) is also fixed —
       see lib/github_image_host.py's URL-liveness polling.
    3. Threads: outbound link posted as the FIRST REPLY, never in the main
       body (see _mirror_to_threads / _split_link_line below) — unchanged
       from before, still applied everywhere.
    4. A closing, genuinely open-ended question is added to Wednesday/
       Thursday knowledge posts and Sunday's poll (not every post, to avoid
       feeling forced) — Threads is reported to weight replies/reposts more
       than likes.
    5. Posting-frequency consistency — unchanged, the fixed weekly schedule
       already satisfies this.
    6. Manual, non-automatable items (seeding initial engagement, the
       reply-guy strategy) are left as human/semi-manual tools — see
       _send_daily_reply_toolkit() below, sent privately to ADMIN_CHAT_ID.
    7. @-mention spam — never used anywhere in this codebase; nothing to fix.

Platforms:
    Telegram  : full support (text, photo, native poll)
    Threads   : text/image posts + native polls (poll_attachment, April 2025)

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
from typing import Optional

from lib.fetch_data import fetch_all, FetchError
from lib.compute_liquidity import (
    compute_net_market_flow,
    compute_net_market_flow_history,
    compute_liquidity_index,
    compute_top_drivers,
)
from lib.generate_card import (
    create_gauge_card,
    create_metric_chart_card,
    create_calendar_card,
    create_term_icon_card,
)
from lib.post_telegram import send_photo, send_text, send_poll, TelegramError
from lib.post_threads import (
    publish_text_post, publish_image_post, publish_poll_post, reply_to_post, ThreadsError,
)
from lib.github_image_host import publish_image_to_repo, ImageHostError
from lib.terms import get_term_of_the_day, format_term_caption
from lib.polls import pick_open_question_for_sunday, GENERIC_LIQUIDITY_POLLS
from lib.llm_content import generate_fact_caption, generate_why_it_matters, generate_calendar_commentary
from lib.reply_templates import generate_reply_snippets, format_reply_toolkit_message
from lib.signal_scanner import get_top_signal
from lib.signal_state import is_on_cooldown, record_signal_posted, COOLDOWN_DAYS
from lib.knowledge_content import build_knowledge_content
from lib.fetch_calendar import (
    get_events_this_month, get_top_upcoming_events, CalendarError,
)

# --- IMPORTANT: confirm this matches your actual live English page URL ---
SITE_URL = os.environ.get("SITE_URL", "https://americayoudongsung.netlify.app/en")

MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = range(7)


# ---------------------------------------------------------------------------
# Threads helpers — never let a Threads failure break the Telegram post.
# LINK STRATEGY: see module docstring point 3.
# ---------------------------------------------------------------------------
def _split_link_line(caption: str, site_url: str) -> tuple[str, str]:
    lines = caption.split("\n")
    kept = [ln for ln in lines if site_url not in ln]
    body = "\n".join(kept).rstrip()
    if body:
        body += "\n\n🔗 Full live dashboard — link in the first reply 👇"
    return body, f"🔗 {site_url}"


def _mirror_to_threads(text: str, image_path: str | None = None, site_url: str | None = SITE_URL) -> Optional[str]:
    """Publishes the main Threads post (link-free body) and posts the link as
    a reply. Returns the published post id (or None if Threads isn't
    configured / the post failed) so callers can attach further replies
    (e.g. Monday's second trend-chart image)."""
    if not os.environ.get("THREADS_USER_ID") or not os.environ.get("THREADS_ACCESS_TOKEN"):
        print("[Threads] Not configured, skipping mirror post.")
        return None

    body, link_text = _split_link_line(text, site_url) if site_url and site_url in text else (text, None)

    post_id = None
    if image_path:
        try:
            print("[Threads] Publishing generated image to repo for a public URL...")
            image_url = publish_image_to_repo(image_path)
            print(f"  -> {image_url}")
            resp = publish_image_post(body, image_url)
            post_id = resp.get("id")
            print("[Threads] Mirrored with image successfully.")
        except (ImageHostError, ThreadsError) as e:
            print(f"[Threads] Image mirror failed, falling back to text-only: {e}", file=sys.stderr)

    if post_id is None:
        try:
            resp = publish_text_post(body)
            post_id = resp.get("id")
            print("[Threads] Mirrored (text-only) successfully.")
        except ThreadsError as e:
            print(f"[Threads] Mirror failed (non-fatal): {e}", file=sys.stderr)
            return None

    if post_id and link_text:
        try:
            reply_to_post(post_id, link_text)
            print("[Threads] Link posted as first reply.")
        except ThreadsError as e:
            print(f"[Threads] Reply-with-link failed (non-fatal, main post still up): {e}", file=sys.stderr)

    return post_id


def _reply_with_image(post_id: str | None, text: str, image_path: str) -> None:
    """Attaches a second image as a reply to an existing Threads post — used
    for Monday's NETMARKETFLOW trend chart, so the main feed shows one post
    per slot while the thread carries both visuals."""
    if not post_id or not os.environ.get("THREADS_USER_ID") or not os.environ.get("THREADS_ACCESS_TOKEN"):
        return
    try:
        image_url = publish_image_to_repo(image_path)
        reply_to_post(post_id, text, image_url=image_url)
        print("[Threads] Trend chart posted as a second reply.")
    except (ImageHostError, ThreadsError) as e:
        print(f"[Threads] Trend-chart reply failed (non-fatal): {e}", file=sys.stderr)


def _strip_html(text: str) -> str:
    for tag in ("<b>", "</b>", "<i>", "</i>"):
        text = text.replace(tag, "")
    return text


# ---------------------------------------------------------------------------
# Monday: Weekly Liquidity Index (percentile gauge) + NETMARKETFLOW trend
# ---------------------------------------------------------------------------
def run_monday_liquidity_result(data_store: dict | None = None) -> int:
    print("[1/5] Fetching data...")
    data_store = data_store or fetch_all()

    print("[2/5] Computing this week's Liquidity Index (percentile-based, matches the site)...")
    index_data = compute_liquidity_index(data_store)
    result = compute_net_market_flow(data_store)
    top_drivers = compute_top_drivers(result, top_n=2)
    print(f"  -> {index_data['percentile']}/100 — {index_data['status']['text_en']}")

    print("[3/5] Generating gauge card (no date, dome-up, matches site geometry)...")
    gauge_path = create_gauge_card(index_data, top_drivers)

    driver_sentence = " and ".join(
        f"{d['label']} ({'+' if d['value'] > 0 else ''}{d['value']:.1f} B$/Wk)" for d in top_drivers
    )
    why = generate_why_it_matters(
        "This week's Liquidity Index",
        f"Index: {index_data['percentile']}/100 ({index_data['status']['text_en']}). "
        f"Driven mainly by {driver_sentence}.",
    )
    caption1 = (
        f"<b>US Market Liquidity — Weekly Index</b>\n\n"
        f"Index: <b>{index_data['percentile']}/100</b> — {index_data['status']['text_en']}\n\n"
        f"Driven mainly by {driver_sentence}.\n\n"
        f"<i>Why it matters:</i> {why}\n\n"
        f"👉 For full details, check the page: {SITE_URL}"
    )

    print("[4/5] Posting the gauge...")
    send_photo(gauge_path, caption1)
    post_id = _mirror_to_threads(_strip_html(caption1), image_path=gauge_path)

    print("[5/5] Building + posting the NETMARKETFLOW 52-week trend chart...")
    history = compute_net_market_flow_history(data_store, weeks=52)
    chart_values = [h["net_market_flow"] for h in history]
    chart_dates = [h["as_of_date"] for h in history]
    trend_path = create_metric_chart_card(
        title="Market Total Net Liquidity Supply (NETMARKETFLOW)",
        ticker="NETMARKETFLOW",
        chart_values=chart_values,
        chart_dates=chart_dates,
        unit="B$/Wk",
        subtitle="The underlying weekly dollar figure behind this week's Index.",
    )
    caption2 = (
        "<b>52-Week Trend — Net Market Liquidity Flow</b>\n\n"
        "The raw weekly dollar figure the Liquidity Index above is ranked against."
    )
    send_photo(trend_path, caption2)
    _reply_with_image(post_id, "📈 " + caption2.split('\n\n')[1], trend_path)

    print("Done! (Monday liquidity result)")
    return 0


# ---------------------------------------------------------------------------
# Tuesday: this month's econ calendar (image) + top-3 + LLM commentary
# ---------------------------------------------------------------------------
def run_tuesday_calendar() -> int:
    print("[1/4] Fetching this month's FRED release calendar...")
    try:
        events = get_events_this_month()
    except CalendarError as e:
        print(f"[WARN] Calendar fetch failed, skipping gracefully: {e}", file=sys.stderr)
        return 0
    print(f"  -> {len(events)} events this month")

    print("[2/4] Ranking the top-3 upcoming releases...")
    top3 = get_top_upcoming_events(events, n=3)

    why = ""
    if top3:
        print(f"  -> most important: {top3[0]['name']} on {top3[0]['date']}")
        why = generate_calendar_commentary(top3[0], top3)

    print("[3/4] Generating the calendar card image...")
    now = datetime.now(timezone.utc)
    month_label = now.strftime("%B %Y")
    cal_path = create_calendar_card(events, now.year, now.month)

    print("[4/4] Posting...")
    lines = [f"<b>{month_label} — What to Watch</b>\n"]
    if top3:
        lines.append("Top releases this month:")
        for i, e in enumerate(top3, 1):
            lines.append(f"{i}. {e['name']} — {e['date'].strftime('%b %d')}")
        lines.append("")
        lines.append(f"<i>Why it matters:</i> {why}")
    else:
        lines.append("No major upcoming releases left this month.")
    lines.append("")
    lines.append(f"👉 Full calendar: {SITE_URL}")
    caption = "\n".join(lines)

    send_photo(cal_path, caption)
    _mirror_to_threads(_strip_html(caption), image_path=cal_path)

    print("Done! (Tuesday calendar)")
    return 0


# ---------------------------------------------------------------------------
# Wednesday AND Thursday: IDENTICAL knowledge routine (same function, same
# chart style, same posting time — see module docstring).
# ---------------------------------------------------------------------------
def run_knowledge_content(data_store: dict | None = None) -> int:
    print("[1/4] Fetching data...")
    data_store = data_store or fetch_all()

    print("[2/4] Picking this week's knowledge topic...")
    content = build_knowledge_content(data_store)
    if not content:
        print("[WARN] No usable data for this week's topic, skipping gracefully.")
        return 0
    print(f"  -> ({content['pool']}) {content['title']}")

    print("[3/4] Generating chart card...")
    chart_path = create_metric_chart_card(
        title=content["title"],
        ticker=content["ticker"],
        chart_values=content["chart_values"],
        chart_dates=content["chart_dates"],
        unit=content["unit"],
    )

    print("[4/4] Posting...")
    why = generate_why_it_matters(
        content["title"],
        f"Current value: {content['current_value']}{content['unit']}. {content['explainer']}",
    )
    caption = (
        f"<b>{content['title']}</b>\n\n"
        f"{content['explainer']}\n\n"
        f"<i>Why it matters right now:</i> {why}\n\n"
        f"💬 Does this match what you're seeing elsewhere — curious how others read it.\n\n"
        f"👉 Full charts & data: {SITE_URL}"
    )
    send_photo(chart_path, caption)
    _mirror_to_threads(_strip_html(caption), image_path=chart_path)

    print("Done! (knowledge content)")
    return 0


# ---------------------------------------------------------------------------
# Friday: Term of the Day (illustrated monogram card)
# ---------------------------------------------------------------------------
def run_friday_term() -> int:
    print("[1/3] Picking today's term...")
    term_entry = get_term_of_the_day()
    print(f"  -> {term_entry['term']}")

    print("[2/3] Generating the illustrated term card...")
    card_path = create_term_icon_card(term_entry["term"], term_entry["definition"], term_entry["badge"])

    print("[3/3] Posting...")
    why = generate_why_it_matters(term_entry["term"], term_entry["definition"])
    caption = format_term_caption(term_entry, SITE_URL, why_it_matters=why)
    send_photo(card_path, caption)
    _mirror_to_threads(_strip_html(caption), image_path=card_path)

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

    print("[2/2] Mirroring to Threads as a NATIVE poll...")
    if os.environ.get("THREADS_USER_ID") and os.environ.get("THREADS_ACCESS_TOKEN"):
        try:
            publish_poll_post(f"💬 {question}", options)
            print("[Threads] Native poll posted successfully.")
        except ThreadsError as e:
            print(f"[Threads] Native poll failed, falling back to text: {e}", file=sys.stderr)
            _mirror_to_threads(f"💬 {question}\n(Reply with your take!)")
    else:
        print("[Threads] Not configured, skipping mirror post.")

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

    # DEDUP: the underlying weekly-cadence series only actually change once a
    # week, so without this check the exact same signal would fire and get
    # posted on every run in between — this is the repeat-content fix. Only
    # the single top signal is checked (not a fallback list) — if it's on
    # cooldown, we skip posting entirely today rather than reaching for a
    # weaker second-best signal.
    if is_on_cooldown(signal["ticker"], signal["signal_type"]):
        print(f"[Signal Scan] '{signal['ticker']}:{signal['signal_type']}' was already posted within the "
              f"last {COOLDOWN_DAYS} days — skipping to avoid repeat content.")
        return 0

    chart_path = create_metric_chart_card(
        title=signal["label"],
        ticker=signal["ticker"],
        chart_values=signal["chart_values"],
        chart_dates=signal["chart_dates"],
        unit=signal["unit"],
        badge_text=signal["signal_type"].replace("_", " ").upper()[:20],
    )

    why = generate_why_it_matters(signal["label"], signal["fact_text"])
    caption = generate_fact_caption(
        fact_text=signal["fact_text"],
        ticker=signal["ticker"],
        current_value=signal["current_value"],
        unit=signal["unit"],
        site_url=SITE_URL,
        why_it_matters=why,
    )

    send_photo(chart_path, caption)
    _mirror_to_threads(_strip_html(caption), image_path=chart_path)
    record_signal_posted(signal["ticker"], signal["signal_type"])
    print("[Signal Scan] Posted.")
    return 0


def _send_daily_reply_toolkit(data_store: dict | None = None) -> None:
    """Optional, private, manual-use-only: today's reply snippets for the
    'reply guy' growth strategy (commenting on other accounts' posts —
    effective for follower growth, but the actual commenting is a human
    action, not something this bot does on its own). Never posted publicly."""
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
        elif weekday == TUESDAY:
            rc = run_tuesday_calendar()
        elif weekday in (WEDNESDAY, THURSDAY):
            rc = run_knowledge_content(data_store)
        elif weekday == FRIDAY:
            rc = run_friday_term()
        elif weekday == SUNDAY:
            rc = run_sunday_engagement()
        else:  # Saturday — no scheduled main post
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
