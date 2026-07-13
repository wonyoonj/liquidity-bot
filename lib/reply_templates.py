# -*- coding: utf-8 -*-
"""
Generates a handful of short, copy-paste-ready reply snippets for the
"reply guy" growth strategy: manually replying to bigger finance/crypto/stock
accounts with a genuinely useful data point + your link.

IMPORTANT: these are NOT auto-posted anywhere. Auto-replying to other
people's posts at scale reads as spam and risks account restrictions.
This module only prepares text for a human to read, pick from, and paste
in themselves — see the "reply toolkit" message sent to ADMIN_CHAT_ID in
daily_post.py.
"""
from __future__ import annotations

import os
import requests

# Each snippet targets a different kind of post you might be replying to,
# so you always have something that fits the context.
CONTEXTS = [
    ("crypto", "a reply to a Bitcoin/crypto-focused post, connecting risk-asset "
               "sentiment to this week's dollar liquidity conditions"),
    ("stocks", "a reply to a stock market / equities post, connecting market "
               "direction to this week's liquidity backdrop"),
    ("macro", "a reply to a general macro/Fed/economy post, adding a concrete "
              "liquidity data point as supporting context"),
    ("question", "a reply that ends with a genuine question, inviting the "
                 "original poster or other readers to share their view"),
]


def _build_prompt(metrics: dict, context_label: str, context_instruction: str, site_url: str) -> str:
    sign = "+" if metrics.get("net_market_flow", 0) > 0 else ""
    return (
        "Write ONE short reply (under 220 characters total, plain text, no hashtags, "
        "no markdown, sounds like a real person adding useful context — not an ad, "
        "not pushy) suitable for replying to someone else's finance/crypto/stock post on "
        "social media. This is " + context_instruction + ".\n\n"
        "It must naturally include this data point (paraphrase it, don't just dump numbers): "
        f"this week's US market net liquidity flow is {sign}{metrics.get('net_market_flow')} "
        f"B$/Week ({metrics.get('state_label', '')}).\n\n"
        f"End with this link on its own short mention (not a hard sell): {site_url}\n\n"
        "Output only the reply text, nothing else."
    )


def _call_gemini(prompt: str, timeout: int = 20) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    resp = requests.post(
        url, params={"key": api_key},
        json={"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {"temperature": 0.95, "maxOutputTokens": 100}},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


def _call_openai(prompt: str, timeout: int = 20) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}],
              "temperature": 0.95, "max_tokens": 100},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _fallback_snippet(metrics: dict, context_label: str, site_url: str) -> str:
    sign = "+" if metrics.get("net_market_flow", 0) > 0 else ""
    val = metrics.get("net_market_flow", 0)
    state = metrics.get("state_label", "")
    templates = {
        "crypto": f"Worth noting: US dollar liquidity is running {sign}{val} B$/Week this week ({state}) — a backdrop that tends to matter for risk assets like BTC. Tracking it here: {site_url}",
        "stocks": f"Adding some macro context: net market liquidity is at {sign}{val} B$/Week this week ({state}). Been tracking the weekly flow here: {site_url}",
        "macro": f"This week's US net liquidity flow: {sign}{val} B$/Week ({state}) — Fed balance sheet, TGA, and MMF flows combined. Full breakdown: {site_url}",
        "question": f"This week's liquidity flow is {sign}{val} B$/Week ({state}) — curious how others are reading that right now? More context: {site_url}",
    }
    return templates.get(context_label, templates["macro"])


def generate_reply_snippets(metrics: dict, site_url: str, provider: str | None = None) -> list[dict]:
    """Returns a list of {"context": str, "text": str} — one per CONTEXTS entry,
    ready to copy-paste. Falls back to templates per-snippet if the LLM call fails."""
    provider = (provider or os.environ.get("LLM_PROVIDER", "gemini")).lower()
    caller = _call_openai if provider == "openai" else _call_gemini

    results = []
    for context_label, context_instruction in CONTEXTS:
        prompt = _build_prompt(metrics, context_label, context_instruction, site_url)
        try:
            text = caller(prompt)
        except Exception:
            text = _fallback_snippet(metrics, context_label, site_url)
        results.append({"context": context_label, "text": text})
    return results


def format_reply_toolkit_message(snippets: list[dict], as_of_date: str) -> str:
    labels = {
        "crypto": "🪙 For crypto/BTC posts",
        "stocks": "📈 For stock market posts",
        "macro": "🏦 For general macro/Fed posts",
        "question": "❓ For engagement (ends in a question)",
    }
    lines = [f"🛠️ <b>Today's Reply Toolkit</b> (as of {as_of_date})", "",
             "Copy-paste whichever fits when replying to other accounts. Don't spam — "
             "use 1 per post, only where it's genuinely relevant.\n"]
    for s in snippets:
        lines.append(f"{labels.get(s['context'], s['context'])}:")
        lines.append(s["text"])
        lines.append("")
    return "\n".join(lines).strip()
