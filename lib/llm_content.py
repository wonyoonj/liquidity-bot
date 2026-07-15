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
"""
from __future__ import annotations

import os
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
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


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
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


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


def generate_angle_commentary(metrics: dict, angle: str | None = None) -> str:
    angle = angle or random.choice(ANGLES)
    provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
    prompt = _build_prompt(metrics, angle)

    try:
        if provider == "openai":
            return _call_openai(prompt)
        return _call_gemini(prompt)
    except Exception:
        # Never let commentary generation break the whole post.
        return _fallback_sentence(metrics, angle)


def generate_fact_caption(fact_text: str, ticker: str, current_value: float, unit: str,
                            site_url: str) -> str:
    """Barchart-style single-fact caption. The fact itself (fact_text) is
    already numerically grounded and deterministic (see signal_scanner.py) —
    the LLM's only job is to rephrase it into a punchier, more natural-sounding
    single sentence, in the terse 'headline + emoji' style, NOT to add new
    claims or explanation. Falls back to the raw fact_text unmodified if the
    LLM is unavailable, which is already a perfectly usable caption on its own."""
    provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
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
        caller = _call_openai if provider == "openai" else _call_gemini
        headline = caller(prompt)
    except Exception:
        headline = fact_text  # the deterministic fact is already a valid caption on its own

    return f"{headline}\n\n👉 {site_url}\n#USLiquidity #{ticker} #FederalReserve"


def generate_open_question(indicator_label: str, context_note: str = "") -> str:
    """Idea #10: an open opinion question about a specific liquidity indicator,
    for Sunday content / Threads engagement posts."""
    provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
    prompt = (
        "Write ONE short, genuinely open-ended question (under 200 characters, plain text, "
        f"no hashtags) inviting an English-speaking finance audience to share their opinion "
        f"about {indicator_label}. Context: {context_note}. "
        "Do not answer the question yourself. Output only the question."
    )
    try:
        if provider == "openai":
            return _call_openai(prompt)
        return _call_gemini(prompt)
    except Exception:
        return f"What's your take on the recent move in {indicator_label}? Signal, or noise?"
