# -*- coding: utf-8 -*-
"""
Uses an LLM (Gemini, OpenAI, or Groq via LLM_PROVIDER env var) to write
daily financial commentary, snapshot captions, and curated news posts.

Includes robust multi-provider failover (Gemini -> OpenAI -> Groq)
and deterministic text fallbacks if all LLMs fail.
"""
from __future__ import annotations

import os
import re
import json
import random
import requests
from typing import Optional

ANGLES = ["comparison", "record", "cause", "question", "warning"]

ANGLE_INSTRUCTIONS = {
    "comparison": "Compare this week's value to the historical average given. Be specific with numbers.",
    "record": "Highlight how this week ranks against recent history (e.g. 'strongest in N weeks') using the rank info given.",
    "cause": "Give a plausible one-line explanation for what's driving this week's number, referencing the specific component (TGA, Fed balance sheet, or MMF flows) that moved most.",
    "question": "End with a short, genuinely open-ended question inviting readers to share their read on this week's number. Do not answer it yourself.",
    "warning": "If (and only if) this week represents a meaningful shift in direction (e.g. crossing from supply to drain or vice versa), frame it as a notable turning point. Otherwise pick a neutral observation instead.",
}


def _extract_json_str(text: str) -> str:
    """Helper to extract clean JSON object string from LLM responses even if they
    contain markdown tags or conversational filler.
    """
    text = text.strip()
    # Strip markdown code fences if present
    if "```" in text:
        match = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

    # Find first { or [ and last } or ]
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    return text


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
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    
    # URL 마크다운 문법 제거 -> 순수 URL 문자열로 수정
    url = f"[https://generativelanguage.googleapis.com/v1beta/models/](https://generativelanguage.googleapis.com/v1beta/models/){model}:generateContent"
    
    resp = requests.post(
        url,
        params={"key": api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.9, "maxOutputTokens": 300},
        },
        timeout=timeout,
    )
    if not resp.ok:
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
    
    # URL 마크다운 문법 제거 -> 순수 URL 문자열로 수정
    url = "[https://api.openai.com/v1/chat/completions](https://api.openai.com/v1/chat/completions)"
    
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.9,
            "max_tokens": 300,
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


def _call_groq(prompt: str, timeout: int = 20) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set")
    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    
    # URL 마크다운 문법 제거 -> 순수 URL 문자열로 수정
    url = "[https://api.groq.com/openai/v1/chat/completions](https://api.groq.com/openai/v1/chat/completions)"
    
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.9,
            "max_tokens": 300,
        },
        timeout=timeout,
    )
    if not resp.ok:
        raise RuntimeError(f"Groq API {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Groq response shape unexpected: {data}") from e


def _call_llm(prompt: str, timeout: int = 20) -> str:
    preferred = os.environ.get("LLM_PROVIDER", "gemini").lower()
    providers = {
        "gemini": ("GEMINI_API_KEY", _call_gemini),
        "groq": ("GROQ_API_KEY", _call_groq),
        "openai": ("OPENAI_API_KEY", _call_openai),
    }
    order = [preferred] + [name for name in providers if name != preferred]

    last_error: Optional[Exception] = None
    attempted = []
    for name in order:
        api_key_env, caller = providers.get(name, (None, None))
        if caller is None or not os.environ.get(api_key_env):
            continue
        attempted.append(name)
        try:
            return caller(prompt, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            last_error = e
            remaining = [n for n in order if n not in attempted and os.environ.get(providers[n][0])]
            print(f"[llm_content] {name} call failed ({e}); "
                  f"{'falling back to ' + remaining[0] + '...' if remaining else 'no other provider configured.'}")

    if not attempted:
        raise RuntimeError(
            "No LLM provider is configured — set GEMINI_API_KEY, GROQ_API_KEY, and/or OPENAI_API_KEY."
        )
    raise RuntimeError(f"All configured LLM providers failed ({', '.join(attempted)}). Last error: {last_error}")


def _fallback_sentence(metrics: dict, angle: str) -> str:
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


def generate_why_it_matters(topic_label: str, context: str, assessment: Optional[dict] = None) -> str:
    assessment_line = ""
    if assessment and assessment.get("status") not in (None, "unknown"):
        assessment_line = (
            f"\nExplicit standard already shown to the reader elsewhere in this post: "
            f"{assessment.get('status_label', '')}. Do NOT restate this standard or say "
            f"whether it's good/bad again — that's already covered. Trend-based risk data "
            f"you should build your answer from: {assessment.get('risk_note', '')}"
        )

    prompt = (
        "In ONE short sentence (under 140 characters total), tell a retail investor audience "
        "the forward-looking risk or trend implication of the following data point. "
        "If trend-based risk data is given below, base your answer on it, in your own words — "
        "do not just copy it verbatim. "
        "Tone: calm, informational, matter-of-fact — like a financial news ticker, not "
        "hype or clickbait. No emoji, no exclamation marks, no hashtags, no markdown. "
        "Do not invent any numbers not given below.\n\n"
        f"Topic: {topic_label}\n"
        f"Context: {context}"
        f"{assessment_line}\n\n"
        "Output only the one sentence, nothing else."
    )
    try:
        return _call_llm(prompt).strip()
    except Exception as e:  # noqa: BLE001
        print(f"[llm_content] generate_why_it_matters failed, using fallback: {e}")
        if assessment and assessment.get("risk_note"):
            return assessment["risk_note"]
        return (
            f"{topic_label} is a direct input into current US dollar liquidity "
            f"conditions, which tend to move alongside broader asset prices."
        )


def generate_calendar_commentary(top_event: dict, other_events: list[dict]) -> str:
    others = ", ".join(e["name"] for e in other_events if e is not top_event) or "no other major releases"
    prompt = (
        "In ONE short sentence (under 160 characters total), tell a retail investor "
        "audience WHY the following upcoming US economic release is worth watching this month. "
        "Tone: calm, informational, matter-of-fact — no hype, no emoji, no hashtags, no "
        "exclamation marks, no markdown. Do not invent any numbers, forecasts, or figures "
        "not given below.\n\n"
        f"Most important upcoming release: {top_event['name']} on {top_event['date']}\n"
        f"Also on the calendar this month: {others}\n\n"
        "Output only the one sentence, nothing else."
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
                          site_url: str, why_it_matters: str = "", status_line: str = "") -> str:
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
        headline = fact_text

    parts = [headline]
    if status_line:
        parts += ["", f"<b>Status:</b> {status_line}"]
    if why_it_matters:
        parts += ["", f"<i>Why it matters:</i> {why_it_matters}"]
    parts += ["", f"👉 {site_url}"]
    return "\n".join(parts)


def pick_and_write_news(candidates: list[dict]) -> dict | None:
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
        "  - \"summary\": ONE sentence (under 160 characters) paraphrasing what "
        "happened, entirely in your own words — do not quote the snippet directly.\n"
        "  - \"impact\": ONE short sentence (under 140 characters), plain and direct, "
        "on the expected effect on US dollar liquidity or market conditions. If "
        "genuinely uncertain, say so plainly rather than guessing confidently.\n\n"
        "Respond with ONLY a JSON object, no markdown fences, no other text:\n"
        '{"selected_index": <int>, "headline": "...", "summary": "...", "impact": "..."}'
    )
    try:
        raw = _call_llm(prompt, timeout=25)
        clean_json = _extract_json_str(raw)
        data = json.loads(clean_json)
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
        "image_url": chosen.get("image_url"),
        "_article_link": chosen.get("link"),
    }


def pick_and_write_top4(candidates: list[dict], count: int = 4) -> list[dict] | None:
    if not candidates:
        return None

    count = max(1, min(count, len(candidates)))

    listing = "\n".join(
        f"[{i}] {c['title']} — {c['summary'][:220]}"
        for i, c in enumerate(candidates)
    )
    item_schema = ", ".join(
        ['{"selected_index": <int>, "headline": "...", "bullet": "..."}'] * count
    )
    prompt = (
        f"You are curating a daily \"Top {count} Financial Headlines\" summary post for a "
        "social media account, based on today's Reuters Business & Finance headlines below "
        "(short snippets only, not full articles).\n\n"
        f"{listing}\n\n"
        f"Step 1: Choose the {count} most significant and CLEARLY DISTINCT stories — avoid "
        "picking two entries about the same underlying event. Prefer market-moving stories: "
        "central bank / interest rate policy, major market/index moves, commodities, and "
        "major corporate earnings, when present among the candidates.\n"
        "Step 2: For EACH pick, write, entirely in your OWN words (never copy phrasing from "
        "the snippet):\n"
        "  - \"headline\": a short, punchy, non-clickbait headline, under 65 characters "
        "(e.g. \"US Fed Announces Interest Rate Outlook\").\n"
        "  - \"bullet\": ONE short supporting-detail sentence, under 110 characters, plain "
        "and factual — no hashtags, no emoji.\n\n"
        f"Respond with ONLY a JSON object, no markdown fences, no other text, exactly "
        f"{count} item(s):\n"
        f'{{"items": [{item_schema}]}}'
    )
    try:
        raw = _call_llm(prompt, timeout=30)
        clean_json = _extract_json_str(raw)
        data = json.loads(clean_json)
    except Exception as e:  # noqa: BLE001
        print(f"[llm_content] pick_and_write_top4 failed/unparseable: {e}")
        return None

    items = data.get("items")
    if not isinstance(items, list):
        return None

    results = []
    used_indices: set = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        idx = item.get("selected_index")
        headline = (item.get("headline") or "").strip()
        bullet = (item.get("bullet") or "").strip()
        if not isinstance(idx, int) or idx < 0 or idx >= len(candidates):
            continue
        if idx in used_indices or not headline or not bullet:
            continue
        used_indices.add(idx)
        chosen = candidates[idx]
        results.append({
            "id": chosen["id"],
            "title": chosen["title"],
            "headline": headline,
            "bullet": bullet,
            "image_url": chosen.get("image_url"),
            "_article_link": chosen.get("link"),
        })
        if len(results) == count:
            break

    if not results:
        return None
    return results


def generate_open_question(indicator_label: str, context_note: str = "") -> str:
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
