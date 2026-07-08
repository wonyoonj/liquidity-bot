# -*- coding: utf-8 -*-
"""
'오늘의 한 줄 요약' 카드뉴스 이미지를 생성합니다. (정사각형, SNS/텔레그램 공유용)
폰트는 fonts/ 폴더에 포함된 나눔고딕을 사용합니다 (한글 깨짐 방지).
"""
from __future__ import annotations

import os
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(BASE_DIR, "fonts")

CANVAS_SIZE = (1080, 1080)
BG_COLOR = (247, 248, 250)
TEXT_DARK = (33, 37, 41)
TEXT_GRAY = (108, 117, 125)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = os.path.join(FONT_DIR, name)
    return ImageFont.truetype(path, size)


def create_summary_card(
    net_market_flow: float,
    state: dict,
    as_of_date: str,
    trend_text: str = "",
    site_name: str = "원뎅이의 미국 유동성 현황",
    out_path: str = "output/summary_card.png",
) -> str:
    img = Image.new("RGB", CANVAS_SIZE, color=BG_COLOR)
    draw = ImageDraw.Draw(img)

    accent = state["color"]
    W, H = CANVAS_SIZE

    # 상단 컬러 밴드
    draw.rectangle([0, 0, W, 140], fill=accent)

    font_brand = _font("NanumGothic-Bold.ttf", 36)
    font_date = _font("NanumGothic-Regular.ttf", 28)
    font_label = _font("NanumGothic-Bold.ttf", 40)
    font_number = _font("NanumGothic-ExtraBold.ttf", 108)
    font_state = _font("NanumGothic-ExtraBold.ttf", 52)
    font_trend = _font("NanumGothic-Regular.ttf", 32)
    font_footer = _font("NanumGothic-Regular.ttf", 24)

    # 상단 밴드 텍스트
    draw.text((50, 45), site_name, font=font_brand, fill="white")
    date_text = f"{as_of_date} 기준"
    date_w = draw.textlength(date_text, font=font_date)
    draw.text((W - 50 - date_w, 52), date_text, font=font_date, fill="white")

    # 본문 라벨
    draw.text((50, 210), "이번 주 시장(Market) Total 유동 공급량", font=font_label, fill=TEXT_GRAY)

    # 숫자 (핵심 지표)
    sign = "+" if net_market_flow > 0 else ""
    number_text = f"{sign}{net_market_flow:.1f}"
    draw.text((50, 280), number_text, font=font_number, fill=accent)

    num_w = draw.textlength(number_text, font=font_number)
    draw.text((50 + num_w + 20, 380), "B$ / Week", font=font_label, fill=TEXT_GRAY)

    # 상태 배지
    badge_y = 520
    draw.rounded_rectangle([50, badge_y, 50 + 700, badge_y + 90], radius=45, fill=accent)
    state_text = state["text_ko"]
    draw.text((90, badge_y + 18), state_text, font=font_state, fill="white")

    # 추세 문구
    if trend_text:
        draw.text((50, badge_y + 120), trend_text.strip(" ·"), font=font_trend, fill=TEXT_GRAY)

    # 하단 설명 박스
    box_y = 760
    draw.rounded_rectangle([50, box_y, W - 50, box_y + 200], radius=20, outline=(222, 226, 230), width=2)
    desc_lines = [
        "· 연준(FED)·정부(TGA)·MMF를 거쳐 시장에",
        "  실제로 순유입된 주간 자금 규모입니다.",
        "· 양수(+)면 유동성 공급, 음수(-)면 흡수 국면입니다.",
    ]
    ly = box_y + 30
    for line in desc_lines:
        draw.text((80, ly), line, font=font_trend, fill=TEXT_DARK)
        ly += 48

    # 푸터
    footer_text = "자료 출처: FRED, Office of Financial Research (OFR)  ·  매일 자동 업데이트"
    draw.text((50, H - 60), footer_text, font=font_footer, fill=TEXT_GRAY)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path)
    return out_path
