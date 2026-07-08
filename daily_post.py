# -*- coding: utf-8 -*-
"""
매일 1회 실행되는 메인 스크립트.

로컬 테스트:
    export TELEGRAM_BOT_TOKEN=xxxx
    export TELEGRAM_CHAT_ID=xxxx
    python daily_post.py

GitHub Actions에서는 .github/workflows/daily_post.yml 이 이 스크립트를
매일 자동으로 실행합니다 (README.md 참고).
"""
from __future__ import annotations

import sys
import traceback

from lib.fetch_data import fetch_all, FetchError
from lib.compute_liquidity import compute_net_market_flow, classify_state, compute_trend_text
from lib.generate_card import create_summary_card
from lib.post_telegram import send_photo, send_text, TelegramError


def build_caption(result: dict, state: dict, trend_text: str) -> str:
    sign = "+" if result["net_market_flow"] > 0 else ""
    return (
        f"{state['emoji']} <b>이번 주 미국 시장 유동성 현황</b> ({result['as_of_date']} 기준)\n\n"
        f"시장(Market) Total 유동 공급량: <b>{sign}{result['net_market_flow']} B$/Week</b>\n"
        f"상태: <b>{state['text_ko']}</b>{trend_text}\n\n"
        f"👉 자세히 보기: https://americayoudongsung.netlify.app/\n"
        f"#미국유동성 #연준 #TGA #역레포 #원뎅이"
    )


def main() -> int:
    try:
        print("[1/4] 데이터 수집 중...")
        data_store = fetch_all()

        print("[2/4] 유동성 지표 계산 중...")
        result = compute_net_market_flow(data_store)
        state = classify_state(result["net_market_flow"])
        trend_text = compute_trend_text(data_store, result)
        print(f"  -> {result}")

        print("[3/4] 카드 이미지 생성 중...")
        image_path = create_summary_card(
            net_market_flow=result["net_market_flow"],
            state=state,
            as_of_date=result["as_of_date"],
            trend_text=trend_text,
        )
        print(f"  -> {image_path}")

        print("[4/4] 텔레그램 전송 중...")
        caption = build_caption(result, state, trend_text)
        send_photo(image_path, caption)
        print("완료!")
        return 0

    except (FetchError, TelegramError, ValueError) as e:
        print(f"[오류] {e}", file=sys.stderr)
        _notify_admin_on_error(str(e))
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"[예상치 못한 오류] {e}", file=sys.stderr)
        traceback.print_exc()
        _notify_admin_on_error(f"예상치 못한 오류: {e}")
        return 1


def _notify_admin_on_error(message: str) -> None:
    """ADMIN_CHAT_ID가 설정돼 있으면 실패 시 본인에게 알림 전송 (선택사항)."""
    import os
    admin_chat_id = os.environ.get("ADMIN_CHAT_ID")
    if not admin_chat_id:
        return
    try:
        send_text(f"🚨 [원뎅이봇] 일일 게시 실패\n{message}", chat_id=admin_chat_id)
    except Exception:
        pass  # 알림 전송 실패는 무시 (원래 오류가 이미 로그에 남아있음)


if __name__ == "__main__":
    sys.exit(main())
