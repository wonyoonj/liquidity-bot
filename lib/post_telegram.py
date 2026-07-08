# -*- coding: utf-8 -*-
"""
Telegram Bot API를 이용한 자동 게시 모듈.
- 승인 절차 없음, 완전 무료.
- 봇 생성: 텔레그램에서 @BotFather 에게 /newbot 전송 -> 토큰 발급
- 채널/그룹에 봇을 '관리자'로 추가 후 chat_id 확보
"""
from __future__ import annotations

import os
import requests


class TelegramError(RuntimeError):
    pass


def _get_credentials(bot_token: str | None, chat_id: str | None) -> tuple[str, str]:
    bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        raise TelegramError(
            "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 환경변수(또는 인자)가 설정되지 않았습니다."
        )
    return bot_token, chat_id


def send_photo(image_path: str, caption: str, bot_token: str | None = None,
                chat_id: str | None = None, timeout: int = 30) -> dict:
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
        raise TelegramError(f"텔레그램 전송 실패: {e} / 응답: {resp.text}") from e
    return resp.json()


def send_text(text: str, bot_token: str | None = None, chat_id: str | None = None,
               timeout: int = 20) -> dict:
    """관리자 알림(에러 발생 시) 등 텍스트만 보낼 때 사용."""
    bot_token, chat_id = _get_credentials(bot_token, chat_id)
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    resp = requests.post(
        url, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=timeout
    )
    try:
        resp.raise_for_status()
    except requests.RequestException as e:
        raise TelegramError(f"텔레그램 텍스트 전송 실패: {e} / 응답: {resp.text}") from e
    return resp.json()
