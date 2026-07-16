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


def _autocrop(img: Image.Image, bg_color=BG_COLOR, margin: int = 28) -> Image.Image:
    """Trims uniform background from all four edges down to the actual content
    bounding box, then adds back a small fixed margin — used so exported cards
    have no wasted whitespace around them (idea: 'crop exactly to the useful
    part, not a loose screenshot')."""
    from PIL import ImageChops
    bg = Image.new(img.mode, img.size, bg_color)
    diff = ImageChops.difference(img, bg)
    bbox = diff.getbbox()
    if not bbox:
        return img
    left, top, right, bottom = bbox
    left = max(0, left - margin)
    top = max(0, top - margin)
    right = min(img.width, right + margin)
    bottom = min(img.height, bottom + margin)
    return img.crop((left, top, right, bottom))


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


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Simple greedy word-wrap. Returns a list of lines that each fit within max_width."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def create_calendar_card(
    events: list[dict],
    site_name: str = "US Liquidity Dashboard",
    out_path: str = "output/calendar_card.png",
) -> str:
    """Monday content: this week's major economic release dates."""
    img = Image.new("RGB", CANVAS_SIZE, color=BG_COLOR)
    draw = ImageDraw.Draw(img)
    W, H = CANVAS_SIZE
    ACCENT = (41, 82, 227)
    WEEKDAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    draw.rectangle([0, 0, W, 140], fill=ACCENT)
    font_brand = _font(34, "Bold")
    font_title = _font(38, "SemiBold")
    font_event_date = _font(30, "Bold")
    font_event_name = _font(28, "Regular")
    font_footer = _font(22, "Regular")
    font_empty = _font(30, "Regular")

    draw.text((50, 50), site_name, font=font_brand, fill="white")
    draw.text((50, 180), "This Week's Major US Economic Releases", font=font_title, fill=TEXT_DARK)

    if not events:
        draw.text((50, 320), "No major releases scheduled this week.", font=font_empty, fill=TEXT_GRAY)
    else:
        y = 300
        row_h = 130
        for e in events[:5]:  # cap at 5 so it always fits the canvas
            d = e["date"]
            weekday = WEEKDAY[d.weekday()]
            date_text = f"{d.strftime('%b %d')} ({weekday})"

            draw.rounded_rectangle([50, y, W - 50, y + row_h - 20], radius=16, fill=(255, 255, 255),
                                    outline=LINE_COLOR, width=2)
            draw.text((80, y + 20), date_text, font=font_event_date, fill=ACCENT)
            draw.text((80, y + 62), e["label"], font=font_event_name, fill=TEXT_DARK)
            y += row_h

    footer_text = "Source: FRED official release calendar  ·  Auto-updated every Monday"
    draw.text((50, H - 60), footer_text, font=font_footer, fill=TEXT_GRAY)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path)
    return out_path


def create_term_card(
    term: str,
    definition: str,
    site_name: str = "US Liquidity Dashboard",
    out_path: str = "output/term_card.png",
) -> str:
    """Saturday content: term-of-the-day glossary card."""
    img = Image.new("RGB", CANVAS_SIZE, color=BG_COLOR)
    draw = ImageDraw.Draw(img)
    W, H = CANVAS_SIZE
    ACCENT = (124, 58, 237)  # purple, distinct from the daily snapshot's palette

    draw.rectangle([0, 0, W, 140], fill=ACCENT)
    font_brand = _font(34, "Bold")
    font_badge = _font(26, "Bold")
    font_term = _font(52, "ExtraBold")
    font_body = _font(32, "Regular")
    font_footer = _font(22, "Regular")

    draw.text((50, 50), site_name, font=font_brand, fill="white")

    draw.rounded_rectangle([50, 190, 320, 234], radius=22, fill=(237, 233, 254))
    draw.text((72, 198), "TERM OF THE DAY", font=font_badge, fill=ACCENT)

    term_lines = _wrap_text(draw, term, font_term, W - 100)
    ty = 270
    for line in term_lines:
        draw.text((50, ty), line, font=font_term, fill=TEXT_DARK)
        ty += 62

    body_lines = _wrap_text(draw, definition, font_body, W - 100)
    by = ty + 30
    for line in body_lines[:10]:  # safety cap so very long definitions don't overflow the canvas
        draw.text((50, by), line, font=font_body, fill=TEXT_DARK)
        by += 44

    footer_text = "A new term every Saturday  ·  US Liquidity Dashboard"
    draw.text((50, H - 60), footer_text, font=font_footer, fill=TEXT_GRAY)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path)
    return out_path


def create_story_card(
    headline: str,
    net_market_flow: float,
    as_of_date: str,
    sub_line: str = "",
    site_name: str = "US Liquidity Dashboard",
    out_path: str = "output/story_card.png",
) -> str:
    """Sunday content: record/streak-style recap card."""
    img = Image.new("RGB", CANVAS_SIZE, color=BG_COLOR)
    draw = ImageDraw.Draw(img)
    W, H = CANVAS_SIZE
    accent = (25, 135, 84) if net_market_flow >= 0 else (220, 53, 69)

    draw.rectangle([0, 0, W, 140], fill=accent)
    font_brand = _font(34, "Bold")
    font_date = _font(26, "Regular")
    font_headline = _font(46, "ExtraBold")
    font_number = _font(88, "ExtraBold")
    font_unit = _font(30, "Medium")
    font_sub = _font(30, "Regular")
    font_footer = _font(22, "Regular")

    draw.text((50, 50), site_name, font=font_brand, fill="white")
    date_text = f"As of {as_of_date}"
    date_w = draw.textlength(date_text, font=font_date)
    draw.text((W - 50 - date_w, 56), date_text, font=font_date, fill="white")

    headline_lines = _wrap_text(draw, headline, font_headline, W - 100)
    hy = 200
    for line in headline_lines[:3]:
        draw.text((50, hy), line, font=font_headline, fill=TEXT_DARK)
        hy += 58

    sign = "+" if net_market_flow > 0 else ""
    number_text = f"{sign}{net_market_flow:.1f}"
    ny = hy + 40
    draw.text((50, ny), number_text, font=font_number, fill=accent)
    num_w = draw.textlength(number_text, font=font_number)
    draw.text((50 + num_w + 20, ny + 30), "B$ / Week", font=font_unit, fill=TEXT_GRAY)

    if sub_line:
        sub_lines = _wrap_text(draw, sub_line, font_sub, W - 100)
        sy = ny + 140
        for line in sub_lines[:4]:
            draw.text((50, sy), line, font=font_sub, fill=TEXT_DARK)
            sy += 42

    footer_text = "Source: FRED, Office of Financial Research (OFR)  ·  Weekly recap every Sunday"
    draw.text((50, H - 60), footer_text, font=font_footer, fill=TEXT_GRAY)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path)
    return out_path


def create_fact_card(
    fact_text: str,
    ticker: str,
    chart_values: list[float],
    chart_dates: list[str],
    unit: str = "$B",
    site_name: str = "US Liquidity Dashboard",
    out_path: str = "output/fact_card.png",
) -> str:
    """Barchart-style single-fact card: short headline + a real line chart
    (the chart is the visual centerpiece, not a decorative afterthought)."""
    img = Image.new("RGB", CANVAS_SIZE, color=BG_COLOR)
    draw = ImageDraw.Draw(img)
    W, H = CANVAS_SIZE
    ACCENT = (17, 24, 39)  # near-black header, closer to Barchart's terminal-like look
    UP = (16, 163, 74)
    DOWN = (220, 38, 38)

    is_up = len(chart_values) >= 2 and chart_values[-1] >= chart_values[0]
    line_color = UP if is_up else DOWN

    draw.rectangle([0, 0, W, 110], fill=ACCENT)
    font_ticker = _font(30, "Bold")
    font_brand = _font(22, "Regular")
    font_headline = _font(40, "Bold")
    font_value = _font(64, "ExtraBold")
    font_unit = _font(26, "Medium")
    font_axis = _font(20, "Regular")
    font_footer = _font(20, "Regular")

    draw.text((50, 30), f"${ticker}", font=font_ticker, fill="white")
    brand_w = draw.textlength(site_name, font=font_brand)
    draw.text((W - 50 - brand_w, 40), site_name, font=font_brand, fill=(200, 200, 210))

    headline_lines = _wrap_text(draw, fact_text, font_headline, W - 100)
    hy = 150
    for line in headline_lines[:3]:
        draw.text((50, hy), line, font=font_headline, fill=TEXT_DARK)
        hy += 50

    # Current value, right below the headline
    if chart_values:
        current = chart_values[-1]
        val_text = f"{current:,.1f}"
        vy = hy + 20
        draw.text((50, vy), val_text, font=font_value, fill=line_color)
        vw = draw.textlength(val_text, font=font_value)
        draw.text((50 + vw + 15, vy + 22), unit, font=font_unit, fill=TEXT_GRAY)
        chart_top = vy + 110
    else:
        chart_top = hy + 60

    # --- Sparkline chart (the visual centerpiece) ---
    chart_left, chart_right = 50, W - 50
    chart_bottom = chart_top + 340
    if len(chart_values) >= 2:
        vmin, vmax = min(chart_values), max(chart_values)
        vrange = (vmax - vmin) or 1.0
        n = len(chart_values)
        step = (chart_right - chart_left) / (n - 1)

        points = []
        for i, v in enumerate(chart_values):
            x = chart_left + i * step
            y = chart_bottom - ((v - vmin) / vrange) * (chart_bottom - chart_top)
            points.append((x, y))

        draw.line(points, fill=line_color, width=5, joint="curve")
        # highlight the final (current) point
        lx, ly = points[-1]
        draw.ellipse([lx - 8, ly - 8, lx + 8, ly + 8], fill=line_color)

        # sparse x-axis labels: first / middle / last date only, to stay clean
        for idx in (0, n // 2, n - 1):
            label = chart_dates[idx][5:]  # MM-DD
            lw = draw.textlength(label, font=font_axis)
            lx2 = chart_left + idx * step
            draw.text((max(0, lx2 - lw / 2), chart_bottom + 15), label, font=font_axis, fill=TEXT_GRAY)

    footer_text = "Source: FRED, Office of Financial Research (OFR)"
    draw.text((50, H - 50), footer_text, font=font_footer, fill=TEXT_GRAY)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path)
    return out_path


def create_gauge_card(
    net_market_flow: float,
    state: dict,
    gauge_angle: float,
    window_changes: List[Dict],
    top_drivers: List[Dict],
    site_name: str = "US Liquidity Dashboard",
    out_path: str = "output/gauge_card.png",
) -> str:
    """Monday content: speedometer-style gauge + 1W-52W % change strip + the
    top-2 drivers behind this week's number. Deliberately has NO date/
    'updated' text anywhere — the goal is a card that reads as evergreen
    'this is the current state' rather than a dated snapshot that looks
    stale the moment a few days pass. Auto-cropped tight around the content."""
    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), color=BG_COLOR)
    draw = ImageDraw.Draw(img)
    accent = state["color"]

    font_brand = _font(32, "Bold")
    font_label = _font(30, "SemiBold")
    font_number = _font(88, "ExtraBold")
    font_unit = _font(28, "Medium")
    font_state = _font(36, "ExtraBold")
    font_change_label = _font(22, "Medium")
    font_change_val = _font(30, "Bold")
    font_driver_head = _font(28, "SemiBold")
    font_driver = _font(26, "Regular")
    font_footer = _font(20, "Regular")

    draw.rectangle([0, 0, W, 110], fill=(17, 24, 39))
    draw.text((50, 38), site_name, font=font_brand, fill="white")

    # --- Speedometer gauge (semicircle) ---
    cx, cy, radius = W // 2, 420, 260
    zone_bounds = [(-90, -45, (220, 53, 69)), (-45, 0, (253, 126, 20)),
                   (0, 45, (255, 193, 7)), (45, 90, (25, 135, 84))]
    thickness = 34
    bbox = [cx - radius, cy - radius, cx + radius, cy + radius]
    for start_deg, end_deg, color in zone_bounds:
        # PIL arc(): 0 deg = 3 o'clock, clockwise. Our gauge is -90..+90 with
        # -90 = left (9 o'clock), +90 = right (3 o'clock), top-half semicircle.
        draw.arc(bbox, start=180 + start_deg, end=180 + end_deg, fill=color, width=thickness)

    # Needle
    import math
    needle_rad = math.radians(180 + gauge_angle)
    needle_len = radius - thickness / 2 - 6
    nx = cx + needle_len * math.cos(needle_rad)
    ny = cy + needle_len * math.sin(needle_rad)
    draw.line([(cx, cy), (nx, ny)], fill=(17, 24, 39), width=8)
    draw.ellipse([cx - 16, cy - 16, cx + 16, cy + 16], fill=(17, 24, 39))

    draw.text((50, 175), "This Week's Net Liquidity Supply", font=font_label, fill=TEXT_GRAY)

    sign = "+" if net_market_flow > 0 else ""
    number_text = f"{sign}{net_market_flow:.1f}"
    num_w = draw.textlength(number_text, font=font_number)
    draw.text((cx - num_w / 2, cy - 60), number_text, font=font_number, fill=accent)
    unit_text = "B$ / Week"
    unit_w = draw.textlength(unit_text, font=font_unit)
    draw.text((cx - unit_w / 2, cy + 40), unit_text, font=font_unit, fill=TEXT_GRAY)

    state_text = state.get("text_en", state.get("text_ko", ""))
    state_w = draw.textlength(state_text, font=font_state)
    badge_w = state_w + 80
    badge_y = cy + radius - 40
    draw.rounded_rectangle([cx - badge_w / 2, badge_y, cx + badge_w / 2, badge_y + 74],
                            radius=37, fill=accent)
    draw.text((cx - state_w / 2, badge_y + 18), state_text, font=font_state, fill="white")

    # --- 1W-52W % change strip ---
    strip_y = badge_y + 130
    draw.text((50, strip_y), "Liquidity Pace — % Change by Window", font=font_label, fill=TEXT_DARK)
    strip_y += 55
    n = len(window_changes)
    box_gap = 20
    box_w = (W - 100 - box_gap * (n - 1)) / n
    for i, wc in enumerate(window_changes):
        bx = 50 + i * (box_w + box_gap)
        draw.rounded_rectangle([bx, strip_y, bx + box_w, strip_y + 130], radius=16,
                                fill=(255, 255, 255), outline=LINE_COLOR, width=2)
        label_w = draw.textlength(wc["label"], font=font_change_label)
        draw.text((bx + box_w / 2 - label_w / 2, strip_y + 16), wc["label"],
                   font=font_change_label, fill=TEXT_GRAY)
        if wc["pct"] is None:
            val_text = "N/A"
            val_color = TEXT_GRAY
        else:
            val_text = f"{'+' if wc['pct'] > 0 else ''}{wc['pct']:.0f}%"
            val_color = (25, 135, 84) if wc["pct"] >= 0 else (220, 53, 69)
        val_w = draw.textlength(val_text, font=font_change_val)
        draw.text((bx + box_w / 2 - val_w / 2, strip_y + 60), val_text,
                   font=font_change_val, fill=val_color)

    # --- Top-2 drivers ---
    drv_y = strip_y + 170
    draw.text((50, drv_y), "Biggest Drivers This Week", font=font_driver_head, fill=TEXT_DARK)
    drv_y += 46
    for d in top_drivers:
        sign_d = "+" if d["value"] > 0 else ""
        line = f"• {d['label']}: {sign_d}{d['value']:.1f} B$/Week"
        draw.text((50, drv_y), line, font=font_driver, fill=TEXT_DARK)
        drv_y += 42

    footer_text = "Source: FRED, Office of Financial Research (OFR)"
    draw.text((50, drv_y + 30), footer_text, font=font_footer, fill=TEXT_GRAY)

    img = _autocrop(img, margin=30)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path)
    return out_path


def create_knowledge_card(
    title: str,
    chart_values: List[float],
    chart_dates: List[str],
    unit: str,
    ticker: str,
    site_name: str = "US Liquidity Dashboard",
    out_path: str = "output/knowledge_card.png",
) -> str:
    """Wednesday content: clean 52-week (or however much history exists)
    line chart for one indicator, used alongside the plain-language
    explainer text (see lib/knowledge_content.py) written in the caption."""
    W, H = 1080, 900
    img = Image.new("RGB", (W, H), color=BG_COLOR)
    draw = ImageDraw.Draw(img)
    ACCENT = (41, 82, 227)

    is_up = len(chart_values) >= 2 and chart_values[-1] >= chart_values[0]
    line_color = (25, 135, 84) if is_up else (220, 53, 69)

    draw.rectangle([0, 0, W, 110], fill=ACCENT)
    font_brand = _font(30, "Bold")
    font_ticker = _font(26, "Regular")
    font_title = _font(38, "SemiBold")
    font_value = _font(58, "ExtraBold")
    font_unit = _font(26, "Medium")
    font_axis = _font(20, "Regular")
    font_footer = _font(20, "Regular")

    draw.text((50, 36), site_name, font=font_brand, fill="white")
    tk = f"${ticker}"
    tk_w = draw.textlength(tk, font=font_ticker)
    draw.text((W - 50 - tk_w, 42), tk, font=font_ticker, fill=(210, 216, 245))

    title_lines = _wrap_text(draw, title, font_title, W - 100)
    ty = 150
    for line in title_lines[:2]:
        draw.text((50, ty), line, font=font_title, fill=TEXT_DARK)
        ty += 48

    if chart_values:
        current = chart_values[-1]
        val_text = f"{current:,.2f}{unit}" if unit == "%" else f"{current:,.1f}"
        vy = ty + 20
        draw.text((50, vy), val_text, font=font_value, fill=line_color)
        if unit != "%":
            vw = draw.textlength(val_text, font=font_value)
            draw.text((50 + vw + 15, vy + 20), unit, font=font_unit, fill=TEXT_GRAY)
        chart_top = vy + 100
    else:
        chart_top = ty + 60

    chart_left, chart_right = 50, W - 50
    chart_bottom = chart_top + 340
    weeks_label = f"Last {len(chart_values)} weeks" if chart_values else ""
    if len(chart_values) >= 2:
        vmin, vmax = min(chart_values), max(chart_values)
        vrange = (vmax - vmin) or 1.0
        n = len(chart_values)
        step = (chart_right - chart_left) / (n - 1)
        points = []
        for i, v in enumerate(chart_values):
            x = chart_left + i * step
            y = chart_bottom - ((v - vmin) / vrange) * (chart_bottom - chart_top)
            points.append((x, y))
        draw.line(points, fill=line_color, width=5, joint="curve")
        lx, ly = points[-1]
        draw.ellipse([lx - 8, ly - 8, lx + 8, ly + 8], fill=line_color)
        for idx in (0, n // 2, n - 1):
            label = chart_dates[idx][5:]
            lw = draw.textlength(label, font=font_axis)
            lx2 = chart_left + idx * step
            draw.text((max(0, lx2 - lw / 2), chart_bottom + 15), label, font=font_axis, fill=TEXT_GRAY)

    draw.text((50, chart_bottom + 50), weeks_label, font=font_axis, fill=TEXT_GRAY)
    footer_text = "Source: FRED  ·  Weekly knowledge series — US Liquidity Dashboard"
    draw.text((50, H - 50), footer_text, font=font_footer, fill=TEXT_GRAY)

    img = _autocrop(img, margin=30)
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
