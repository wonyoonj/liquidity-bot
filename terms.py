# -*- coding: utf-8 -*-
"""
Telegram Bot API client: text, photo, and native poll posting.
"""
from __future__ import annotations

import os
import json
import requests


class TelegramError(RuntimeError):
    pass


def _get_credentials(bot_token, chat_id):
    bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        raise TelegramError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID is not set.")
    return bot_token, chat_id


def send_photo(image_path: str, caption: str, bot_token=None, chat_id=None, timeout: int = 30) -> dict:
    bot_token, chat_id = _get_credentials(bot_token, chat_id)
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    with open(image_path, "rb") as f:
        resp = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
            files={"photo": f},
            timeout=timeout,
        )
    try:
        resp.raise_for_status()
    except requests.RequestException as e:
        raise TelegramError(f"sendPhoto failed: {e} / response: {resp.text}") from e
    return resp.json()


def send_text(text: str, bot_token=None, chat_id=None, timeout: int = 20) -> dict:
    bot_token, chat_id = _get_credentials(bot_token, chat_id)
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    resp = requests.post(
        url, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=timeout
    )
    try:
        resp.raise_for_status()
    except requests.RequestException as e:
        raise TelegramError(f"sendMessage failed: {e} / response: {resp.text}") from e
    return resp.json()


def send_poll(
    question: str,
    options: list[str],
    bot_token=None,
    chat_id=None,
    is_anonymous: bool = True,
    allows_multiple_answers: bool = False,
    timeout: int = 20,
) -> dict:
    """Native Telegram poll. NOTE: Telegram channels require the bot to be an
    admin with 'post messages' rights, same as sendPhoto/sendMessage.
    Question max 300 chars, each option max 100 chars, 2-10 options."""
    bot_token, chat_id = _get_credentials(bot_token, chat_id)
    url = f"https://api.telegram.org/bot{bot_token}/sendPoll"
    resp = requests.post(
        url,
        data={
            "chat_id": chat_id,
            "question": question[:300],
            "options": json.dumps([o[:100] for o in options][:10]),
            "is_anonymous": str(is_anonymous).lower(),
            "allows_multiple_answers": str(allows_multiple_answers).lower(),
        },
        timeout=timeout,
    )
    try:
        resp.raise_for_status()
    except requests.RequestException as e:
        raise TelegramError(f"sendPoll failed: {e} / response: {resp.text}") from e
    return resp.json()
