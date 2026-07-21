# -*- coding: utf-8 -*-
"""
Uses an LLM (Gemini or OpenAI, your choice via LLM_PROVIDER env var) to write
a single varied "angle" sentence for the daily snapshot, so the same number
doesn't get the same boring caption every day (see idea list: comparison /
record / cause / question / warning angles).

Design choice: if the LLM call fails for ANY reason (no key, rate limit,
network hiccup), we fall back to a deterministic template so the daily post
NEVER fails just because of the commentary layer. The core numbers always
ship; the LLM only adds flavor on top.

v2 fix: every fallback path now PRINTS the real exception before falling
back. Previously all `except Exception:` blocks swallowed the error
silently, which made a real, ongoing LLM failure look identical to "working
normally, just using the fallback occasionally" in the Action logs — there
was no way to tell them apart. If you see "[llm_content] ... failed:" lines
in your logs now, that tells you definitively that every post is running on
fallback templates, and shows you the actual reason (bad key, wrong model
name, rate limit, timeout, etc.).

v2 fix 2: generate_why_it_matters()'s fallback sentence no longer starts
with "This matters because..." — every caller already prepends its own
"Why it matters:" / "Why it matters right now:" label, so the old fallback
text produced a visible double-up ("Why it matters: This matters
because..."). Fixed to be a plain sentence with no redundant lead-in.
"""
from __future__ import annotations

import os
import json
import random
import requests

ANGLES = ["comparison", "record", "cause", "question", "warning"]

ANGLE_INSTRUCTIONS = {
    "comparison": "Compare this week's value to the historical average given. Be specific with numbers.",
    "record": "Highlight how this week ranks against recent history (e.g. 'strongest in N weeks') using the rank info given.",
    "cause": "Give a plausible one-line explanation for what's driving this week's number, referencing the specific component (TGA, Fed balance sheet, or MMF flows) that moved most.",
    "question": "End with a short, genuinely open-ended question inviting readers to share their read on this week's number. Do not answer it yourself.",
    "warning": "If (and only if) this week represents a meaningful shift in direction (e.g. crossing from supply to drain or vice versa), frame it as a notable turning point. Otherwise pick a neutral observation instead.",
}


def _build_prompt(metrics: dict, angle: str) -> str:
    return (
        "You are writing ONE short sentence (under 200 characters, plain text, no hashtags, "
        "no markdown) for a social media post about US dollar market liquidity, aimed at "
        "an English-speaking retail investor audience. Be concrete and numbers-driven, never "
        "vague. Do not invent any numbers that aren't given below.\n\n"
        f"Angle to use: {angle}. Instruction: {ANGLE_INSTRUCTIONS[angle]}\n\n"
        "Data:\n"
        f"- This week's net market liquidity flow: {metrics.get('net_market_flow')} B$/Week\n"
        f"- As of date: {metrics.get('as_of_date')}\n"
        f"- Recent average ({metrics.get('window_weeks', 'N')} weeks): {metrics.get('avg')} B$/Week\n"
        f"- Rank this week (1 = strongest supply): {metrics.get('supply_rank')} of {metrics.get('n_weeks')}\n"
        f"- Rank this week (1 = strongest drain): {metrics.get('drain_rank')} of {metrics.get('n_weeks')}\n"
        f"- Current streak: {metrics.get('streak_length')} consecutive weeks of "
        f"{metrics.get('streak_direction')}\n"
        f"- Biggest single component driving this week's move: {metrics.get('biggest_driver', 'n/a')}\n\n"
        "Output only the sentence, nothing else."
    )


def _call_gemini(prompt: str, timeout: int = 20) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    resp = requests.post(
        url,
        params={"key": api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.9, "maxOutputTokens": 120},
        },
        timeout=timeout,
    )
    if not resp.ok:
        # Surface the API's own error body — this is usually the single most
        # useful line for diagnosing "why is this always falling back".
        raise RuntimeError(f"Gemini API {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Gemini response shape unexpected: {data}") from e


def _call_openai(prompt: str, timeout: int = 20) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.9,
            "max_tokens": 120,
        },
        timeout=timeout,
    )
    if not resp.ok:
        raise RuntimeError(f"OpenAI API {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"OpenAI response shape unexpected: {data}") from e


def _call_llm(prompt: str, timeout: int = 20) -> str:
    """Shared dispatch + logging wrapper. Every public generate_* function
    below should call this instead of _call_openai/_call_gemini directly, so
    failures are ALWAYS logged in exactly one place, consistently."""
    provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
    caller = _call_openai if provider == "openai" else _call_gemini
    return caller(prompt, timeout=timeout)


def _fallback_sentence(metrics: dict, angle: str) -> str:
    """Deterministic, no-API-needed backup so the pipeline never breaks."""
    net = metrics.get("net_market_flow", 0)
    avg = metrics.get("avg")
    if angle == "comparison" and avg is not None:
        direction = "faster than" if net > avg else "slower than"
        return f"This week's pace ({net:+.1f} B$/Week) is running {direction} the recent average of {avg:+.1f} B$/Week."
    if angle == "record" and metrics.get("supply_rank") and metrics.get("n_weeks"):
        return f"This ranks #{metrics['supply_rank']} strongest supply week out of the last {metrics['n_weeks']}."
    if angle == "question":
        return "What's your read on this week's number — a real shift, or just noise?"
    return f"Net market liquidity flow this week: {net:+.1f} B$/Week."


def generate_why_it_matters(topic_label: str, context: str) -> str:
    """Short (1-2 sentence), calm, informational explanation of WHY a given
    data point/signal is worth paying attention to right now — used on
    Monday/Wednesday/Thursday/Friday and the urgent scanner. Tone matches
    the rest of this bot: matter-of-fact, no hype, no exclamation marks, no
    emoji, no hashtags. Falls back to a generic-but-still-useful template
    sentence if the LLM call fails, per this module's fail-open design —
    the post never goes out without SOME explanation.

    NOTE: the fallback text deliberately does NOT start with "Why it
    matters" / "This matters because" — every caller already prepends its
    own "Why it matters:" label onto whatever this returns, so doing it here
    too would double up (this was a real bug — see module docstring)."""
    prompt = (
        "In 1-2 short sentences (under 220 characters total), explain to a retail "
        "investor audience WHY the following financial data point matters right now. "
        "Tone: calm, informational, matter-of-fact — like a financial news ticker, not "
        "hype or clickbait. No emoji, no exclamation marks, no hashtags, no markdown. "
        "Do not invent any numbers not given below.\n\n"
        f"Topic: {topic_label}\n"
        f"Context: {context}\n\n"
        "Output only the explanation, nothing else."
    )
    try:
        return _call_llm(prompt).strip()
    except Exception as e:  # noqa: BLE001
        print(f"[llm_content] generate_why_it_matters failed, using fallback: {e}")
        return (
            f"{topic_label} is a direct input into current US dollar liquidity "
            f"conditions, which tend to move alongside broader asset prices."
        )


def generate_calendar_commentary(top_event: dict, other_events: list[dict]) -> str:
    """Tuesday content: 2-3 calm, informational sentences on why the single
    most important upcoming release this month is worth watching, with a
    brief nod to the other top releases. Falls back to a template sentence
    if the LLM call fails."""
    others = ", ".join(e["name"] for e in other_events if e is not top_event) or "no other major releases"
    prompt = (
        "In 2-3 short sentences (under 320 characters total), explain to a retail investor "
        "audience WHY the following upcoming US economic release is worth watching this month, "
        "and briefly note what else is on the calendar. Tone: calm, informational, "
        "matter-of-fact — no hype, no emoji, no hashtags, no exclamation marks, no markdown. "
        "Do not invent any numbers, forecasts, or figures not given below.\n\n"
        f"Most important upcoming release: {top_event['name']} on {top_event['date']}\n"
        f"Also on the calendar this month: {others}\n\n"
        "Output only the explanation, nothing else."
    )
    try:
        return _call_llm(prompt).strip()
    except Exception as e:  # noqa: BLE001
        print(f"[llm_content] generate_calendar_commentary failed, using fallback: {e}")
        return (
            f"{top_event['name']} is the release most likely to move Fed policy expectations "
            f"and short-term liquidity conditions this month, so it's worth watching closely."
        )


def generate_angle_commentary(metrics: dict, angle: str | None = None) -> str:
    angle = angle or random.choice(ANGLES)
    prompt = _build_prompt(metrics, angle)
    try:
        return _call_llm(prompt).strip()
    except Exception as e:  # noqa: BLE001
        print(f"[llm_content] generate_angle_commentary failed, using fallback: {e}")
        return _fallback_sentence(metrics, angle)


def generate_fact_caption(fact_text: str, ticker: str, current_value: float, unit: str,
                            site_url: str, why_it_matters: str = "") -> str:
    """Barchart-style single-fact caption. The fact itself (fact_text) is
    already numerically grounded and deterministic (see signal_scanner.py) —
    the LLM's only job is to rephrase it into a punchier, more natural-sounding
    single sentence, in the terse 'headline + emoji' style, NOT to add new
    claims or explanation. Falls back to the raw fact_text unmodified if the
    LLM is unavailable, which is already a perfectly usable caption on its own.
    No hashtags by design (see reach-strategy notes in daily_post.py)."""
    prompt = (
        "Rewrite the following financial fact as ONE punchy headline-style sentence "
        "for a social media post, in the terse style of accounts like Barchart "
        "(e.g. 'META just closed above its 200-day moving average for the longest "
        "stretch since February'). Rules: under 180 characters, plain text, no "
        "markdown, at most 1-2 emoji used sparingly for emphasis (not decoration), "
        "state the fact directly with NO explanation of why it matters and NO "
        "hedging language. Do not invent any numbers not present in the input.\n\n"
        f"Fact: {fact_text}\n"
        f"Ticker: ${ticker}\n"
        f"Current value: {current_value} {unit}\n\n"
        "Output only the rewritten sentence, nothing else."
    )
    try:
        headline = _call_llm(prompt).strip()
    except Exception as e:  # noqa: BLE001
        print(f"[llm_content] generate_fact_caption failed, using raw fact_text: {e}")
        headline = fact_text  # the deterministic fact is already a valid caption on its own

    parts = [headline]
    if why_it_matters:
        parts += ["", f"<i>Why it matters:</i> {why_it_matters}"]
    parts += ["", f"👉 {site_url}"]
    return "\n".join(parts)


def pick_and_write_news(candidates: list[dict]) -> dict | None:
    """Given a shortlist of candidate news entries (title + short snippet
    only — never the full article), asks the LLM to (1) pick the single one
    most relevant to USD market liquidity / Fed policy / rates, and (2) write
    a short paraphrased summary + a plain expected-impact line, all in ONE
    call. Returns None if the LLM is unavailable or its output can't be
    parsed — callers should treat that as "nothing to post today" rather
    than crash, since fabricating a pick without grounding would be worse.

    COPYRIGHT NOTE: candidates only carry short RSS snippets (already capped
    at 500 chars upstream), and the prompt explicitly instructs the model to
    paraphrase rather than reproduce source wording — consistent with this
    project's copyright-safe-by-design approach throughout."""
    if not candidates:
        return None

    listing = "\n".join(
        f"[{i}] ({c['source_name']}) {c['title']} — {c['summary'][:200]}"
        for i, c in enumerate(candidates)
    )
    prompt = (
        "You are curating ONE daily news item for a social media account that tracks "
        "US dollar market liquidity (Fed balance sheet, Treasury General Account, "
        "reverse repo, bank reserves, short-term rates). Below is a numbered list of "
        "today's candidate headlines with short snippets (not full articles).\n\n"
        f"{listing}\n\n"
        "Step 1: Pick the single index whose story is MOST likely to move US dollar "
        "liquidity conditions or Fed policy expectations. If none are genuinely "
        "relevant, pick -1.\n"
        "Step 2: For your pick, write:\n"
        "  - \"headline\": a short, plain, non-clickbait headline in your OWN words "
        "(under 100 characters). Do not copy phrasing from the snippet.\n"
        "  - \"summary\": 1-2 sentences (under 260 characters) paraphrasing what "
        "happened, entirely in your own words — do not quote the snippet directly.\n"
        "  - \"impact\": 1 short sentence (under 200 characters), plain and direct, "
        "on the expected effect on US dollar liquidity or market conditions. If "
        "genuinely uncertain, say so plainly rather than guessing confidently.\n\n"
        "Respond with ONLY a JSON object, no markdown fences, no other text:\n"
        '{"selected_index": <int>, "headline": "...", "summary": "...", "impact": "..."}'
    )
    try:
        raw = _call_llm(prompt, timeout=25).strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
    except Exception as e:  # noqa: BLE001
        print(f"[llm_content] pick_and_write_news failed/unparseable: {e}")
        return None

    idx = data.get("selected_index", -1)
    if not isinstance(idx, int) or idx < 0 or idx >= len(candidates):
        return None
    if not all(data.get(k) for k in ("headline", "summary", "impact")):
        return None

    chosen = candidates[idx]
    return {
        "id": chosen["id"],
        "title": chosen["title"],
        "source_name": chosen["source_name"],
        "headline": data["headline"].strip(),
        "summary": data["summary"].strip(),
        "impact": data["impact"].strip(),
    }


def generate_open_question(indicator_label: str, context_note: str = "") -> str:
    """Idea #10: an open opinion question about a specific liquidity indicator,
    for Sunday content / Threads engagement posts."""
    prompt = (
        "Write ONE short, genuinely open-ended question (under 200 characters, plain text, "
        f"no hashtags) inviting an English-speaking finance audience to share their opinion "
        f"about {indicator_label}. Context: {context_note}. "
        "Do not answer the question yourself. Output only the question."
    )
    try:
        return _call_llm(prompt).strip()
    except Exception as e:  # noqa: BLE001
        print(f"[llm_content] generate_open_question failed, using fallback: {e}")
        return f"What's your take on the recent move in {indicator_label}? Signal, or noise?"
