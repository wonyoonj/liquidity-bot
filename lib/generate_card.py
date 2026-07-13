# -*- coding: utf-8 -*-
"""
Generates English-language summary card images (daily snapshot + Friday weekly recap).
Uses the Inter variable font (bundled in fonts/) for clean Latin rendering.
"""
from __future__ import annotations

import os
from typing import List, Dict
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(BASE_DIR, "fonts", "Inter-Variable.ttf")

CANVAS_SIZE = (1080, 1080)
BG_COLOR = (247, 248, 250)
TEXT_DARK = (26, 29, 41)
TEXT_GRAY = (108, 117, 125)
LINE_COLOR = (222, 226, 230)


def _font(size: int, weight: str = "Regular") -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(FONT_PATH, size)
    try:
        f.set_variation_by_name(weight)
    except Exception:
        pass  # falls back to default instance if variation isn't available
    return f


def create_summary_card(
    net_market_flow: float,
    state: dict,
    as_of_date: str,
    trend_text: str = "",
    site_name: str = "US Liquidity Dashboard",
    out_path: str = "output/summary_card.png",
) -> str:
    img = Image.new("RGB", CANVAS_SIZE, color=BG_COLOR)
    draw = ImageDraw.Draw(img)
    accent = state["color"]
    W, H = CANVAS_SIZE

    draw.rectangle([0, 0, W, 140], fill=accent)

    font_brand = _font(34, "Bold")
    font_date = _font(26, "Regular")
    font_label = _font(36, "SemiBold")
    font_number = _font(104, "ExtraBold")
    font_unit = _font(34, "Medium")
    font_state = _font(46, "ExtraBold")
    font_trend = _font(30, "Regular")
    font_footer = _font(22, "Regular")

    draw.text((50, 50), site_name, font=font_brand, fill="white")
    date_text = f"As of {as_of_date}"
    date_w = draw.textlength(date_text, font=font_date)
    draw.text((W - 50 - date_w, 56), date_text, font=font_date, fill="white")

    draw.text((50, 210), "This Week's Market Total Net Liquidity Supply", font=font_label, fill=TEXT_GRAY)

    sign = "+" if net_market_flow > 0 else ""
    number_text = f"{sign}{net_market_flow:.1f}"
    draw.text((50, 280), number_text, font=font_number, fill=accent)

    num_w = draw.textlength(number_text, font=font_number)
    draw.text((50 + num_w + 20, 385), "B$ / Week", font=font_unit, fill=TEXT_GRAY)

    badge_y = 520
    state_text = state.get("text_en", state.get("text_ko", ""))
    badge_w = max(700, int(draw.textlength(state_text, font=font_state)) + 80)
    draw.rounded_rectangle([50, badge_y, 50 + badge_w, badge_y + 90], radius=45, fill=accent)
    draw.text((90, badge_y + 20), state_text, font=font_state, fill="white")

    if trend_text:
        draw.text((50, badge_y + 120), trend_text.strip(" ·"), font=font_trend, fill=TEXT_GRAY)

    box_y = 760
    draw.rounded_rectangle([50, box_y, W - 50, box_y + 200], radius=20, outline=LINE_COLOR, width=2)
    desc_lines = [
        "Net weekly dollar flow into the market through the",
        "Fed, Treasury (TGA), and Money Market Funds.",
        "Positive = liquidity supply.  Negative = liquidity drain.",
    ]
    ly = box_y + 30
    for line in desc_lines:
        draw.text((80, ly), line, font=font_trend, fill=TEXT_DARK)
        ly += 46

    footer_text = "Source: FRED, Office of Financial Research (OFR)  ·  Auto-updated daily"
    draw.text((50, H - 60), footer_text, font=font_footer, fill=TEXT_GRAY)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path)
    return out_path


def create_weekly_recap_card(
    history: List[Dict],
    site_name: str = "US Liquidity Dashboard",
    out_path: str = "output/weekly_recap_card.png",
) -> str:
    """Friday content: a simple bar chart of the last N weeks' net market flow."""
    img = Image.new("RGB", CANVAS_SIZE, color=BG_COLOR)
    draw = ImageDraw.Draw(img)
    W, H = CANVAS_SIZE

    UP = (25, 135, 84)
    DOWN = (220, 53, 69)

    draw.rectangle([0, 0, W, 140], fill=(41, 82, 227))
    font_brand = _font(34, "Bold")
    font_title = _font(38, "SemiBold")
    font_axis = _font(22, "Regular")
    font_footer = _font(22, "Regular")
    font_val = _font(20, "Medium")

    draw.text((50, 50), site_name, font=font_brand, fill="white")
    draw.text((50, 180), "Weekly Recap — Net Liquidity Flow", font=font_title, fill=TEXT_DARK)

    recent = history[-8:] if len(history) > 8 else history
    if not recent:
        draw.text((50, 300), "Not enough data to build a recap this week.", font=font_axis, fill=TEXT_GRAY)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        img.save(out_path)
        return out_path

    chart_left, chart_right = 80, W - 80
    chart_top, chart_bottom = 280, 780
    zero_y = (chart_top + chart_bottom) // 2
    draw.line([(chart_left, zero_y), (chart_right, zero_y)], fill=LINE_COLOR, width=2)

    max_abs = max(abs(r["net_market_flow"]) for r in recent) or 1.0
    n = len(recent)
    bar_area_w = chart_right - chart_left
    bar_w = bar_area_w / n * 0.55
    gap = bar_area_w / n

    for i, r in enumerate(recent):
        val = r["net_market_flow"]
        cx = chart_left + gap * i + gap / 2
        bar_h = (abs(val) / max_abs) * ((chart_bottom - chart_top) / 2 - 20)
        color = UP if val >= 0 else DOWN
        if val >= 0:
            draw.rounded_rectangle([cx - bar_w / 2, zero_y - bar_h, cx + bar_w / 2, zero_y], radius=6, fill=color)
        else:
            draw.rounded_rectangle([cx - bar_w / 2, zero_y, cx + bar_w / 2, zero_y + bar_h], radius=6, fill=color)

        label = r["as_of_date"][5:]  # MM-DD
        lw = draw.textlength(label, font=font_axis)
        draw.text((cx - lw / 2, chart_bottom + 15), label, font=font_axis, fill=TEXT_GRAY)

        val_text = f"{'+' if val > 0 else ''}{val:.0f}"
        vw = draw.textlength(val_text, font=font_val)
        val_y = zero_y - bar_h - 28 if val >= 0 else zero_y + bar_h + 8
        draw.text((cx - vw / 2, val_y), val_text, font=font_val, fill=TEXT_DARK)

    latest = recent[-1]["net_market_flow"]
    avg = sum(r["net_market_flow"] for r in recent) / len(recent)
    summary = f"Latest: {latest:+.1f} B$/Week   ·   {len(recent)}-week avg: {avg:+.1f} B$/Week"
    draw.text((50, 830), summary, font=font_title, fill=TEXT_DARK)

    footer_text = "Source: FRED, Office of Financial Research (OFR)  ·  Auto-updated weekly"
    draw.text((50, H - 60), footer_text, font=font_footer, fill=TEXT_GRAY)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path)
    return out_path
