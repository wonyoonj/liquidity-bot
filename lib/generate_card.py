# -*- coding: utf-8 -*-
"""
Generates all card images in one consistent visual language ("Candidate C" —
white rounded card on a light page background, blue accent, pill badges,
gradient-fill line charts) chosen by the user from four design candidates.
Uses the Inter variable font (bundled in fonts/) for clean Latin rendering.

Card functions:
    create_gauge_card()        Monday  — percentile-based Liquidity Index,
                                dome-up speedometer (matches the site's own
                                gauge geometry/labels exactly).
    create_metric_chart_card() Wednesday knowledge + urgent scan + Monday's
                                secondary NETMARKETFLOW trend — a single
                                reusable gradient-fill line chart card.
    create_calendar_card()     Tuesday — this month's FRED release calendar.
    create_term_icon_card()    Friday — glossary term with a large icon
                                (no numeric series to chart, so illustrative
                                instead).
"""
from __future__ import annotations

import os
from typing import List, Dict, Optional
from PIL import Image, ImageDraw, ImageFont, ImageChops

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(BASE_DIR, "fonts", "Inter-Variable.ttf")

# --- Shared "Candidate C" visual language ---------------------------------
PAGE_BG = (241, 243, 247)
CARD_BG = (255, 255, 255)
CARD_BORDER = (230, 232, 238)
TEXT_DARK = (26, 29, 41)
TEXT_BODY = (60, 64, 78)
TEXT_GRAY = (108, 117, 125)
TEXT_FAINT = (150, 155, 165)
LINE_COLOR = (230, 232, 238)
BLUE = (37, 99, 235)
LIGHTBLUE = (219, 234, 254)
GREEN_BG = (220, 252, 231)
GREEN_TX = (21, 128, 61)
RED_BG = (253, 236, 236)
RED_TX = (192, 57, 43)
AMBER_BG = (255, 243, 214)
AMBER_TX = (184, 134, 11)

CANVAS_W = 1080


def _font(size: int, weight: str = "Regular") -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(FONT_PATH, size)
    try:
        f.set_variation_by_name(weight)
    except Exception:
        pass  # falls back to default instance if variation isn't available
    return f


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    words = text.split()
    lines: List[str] = []
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


def _autocrop(img: Image.Image, bg_color=PAGE_BG, margin: int = 30) -> Image.Image:
    """Trims uniform page background from all four edges down to the actual
    content bounding box, then adds back a small fixed margin."""
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


def _new_card(height: int, margin: int = 40):
    """White rounded card on the light page background — every card in this
    file starts from this so the visual language stays identical everywhere."""
    img = Image.new("RGB", (CANVAS_W, height), PAGE_BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([margin, margin, CANVAS_W - margin, height - margin],
                         radius=28, fill=CARD_BG, outline=CARD_BORDER, width=2)
    return img, d


def _pill(d: ImageDraw.ImageDraw, x: int, y: int, text: str, font, fg, bg, align_right: bool = False):
    w = d.textlength(text, font=font) + 30
    x0 = (x - w) if align_right else x
    d.rounded_rectangle([x0, y, x0 + w, y + 40], radius=20, fill=bg)
    d.text((x0 + 15, y + 8), text, font=font, fill=fg)
    return w


def _header(d: ImageDraw.ImageDraw, pad: int, brand_font, ticker_font, ticker: str, site_name: str):
    d.text((pad, 78), site_name, font=brand_font, fill=TEXT_DARK)
    _pill(d, CANVAS_W - pad, 75, f"${ticker}", ticker_font, BLUE, LIGHTBLUE, align_right=True)


def _footer(d: ImageDraw.ImageDraw, pad: int, y: int, font, text: str = "Source: FRED, Office of Financial Research (OFR)"):
    d.text((pad, y), text, font=font, fill=TEXT_FAINT)


# ---------------------------------------------------------------------------
# Monday: percentile-based Liquidity Index, dome-up gauge (matches the site)
# ---------------------------------------------------------------------------
def create_gauge_card(
    index_data: dict,
    top_drivers: List[Dict],
    site_name: str = "US Liquidity Dashboard",
    out_path: str = "output/gauge_card.png",
) -> str:
    """`index_data` is the dict returned by compute_liquidity.compute_liquidity_index().
    NO date/'updated' text anywhere by design — evergreen, not a dated
    snapshot that looks stale a few days later."""
    import math

    H = 1250
    img, d = _new_card(H)
    pad = 70

    f_brand = _font(28, "Bold")
    f_ticker = _font(24, "SemiBold")
    f_label = _font(30, "SemiBold")
    f_val = _font(96, "ExtraBold")
    f_unit = _font(30, "Medium")
    f_explain = _font(22, "Regular")
    f_edge = _font(19, "SemiBold")
    f_badge = _font(26, "Bold")
    f_change_label = _font(21, "Medium")
    f_change_val = _font(28, "Bold")
    f_driver_head = _font(27, "SemiBold")
    f_driver = _font(25, "Regular")
    f_footer = _font(19, "Regular")

    _header(d, pad, f_brand, f_ticker, "USLIQ", site_name)
    d.text((pad, 150), "This Week's Liquidity Index", font=f_label, fill=TEXT_GRAY)

    # --- dome-up gauge, pivot at the BOTTOM of the arc (matches site exactly) ---
    cx = CANVAS_W // 2
    pivot_y = 470
    radius = 230
    thickness = 30
    bbox = [cx - radius, pivot_y - radius, cx + radius, pivot_y + radius]

    steps = 48
    for i in range(steps):
        t0, t1 = i / steps, (i + 1) / steps
        if t0 < 0.5:
            u = t0 / 0.5
            c = (int(77 + u * (255 - 77)), int(171 + u * (212 - 171)), int(247 + u * (59 - 247)))
        else:
            u = (t0 - 0.5) / 0.5
            c = (255, int(212 + u * (107 - 212)), int(59 + u * (107 - 59)))
        d.arc(bbox, start=180 + t0 * 180, end=180 + t1 * 180, fill=c, width=thickness)

    percentile = index_data["percentile"]
    needle_deg = 180 + (percentile / 100) * 180
    needle_rad = math.radians(needle_deg)
    nl = radius - thickness / 2 - 6
    nx, ny = cx + nl * math.cos(needle_rad), pivot_y + nl * math.sin(needle_rad)
    d.line([(cx, pivot_y), (nx, ny)], fill=TEXT_DARK, width=7)
    d.ellipse([cx - 14, pivot_y - 14, cx + 14, pivot_y + 14], fill=TEXT_DARK)

    d.text((cx - radius + 5, pivot_y + 14), "UNDERSUPPLY", font=f_edge, fill=TEXT_FAINT)
    lbl = "FLOODED"
    lw = d.textlength(lbl, font=f_edge)
    d.text((cx + radius - 5 - lw, pivot_y + 14), lbl, font=f_edge, fill=TEXT_FAINT)

    # --- number + plain-English explanation BELOW the gauge (matches site layout) ---
    ny2 = pivot_y + 70
    num_text = str(percentile)
    nw = d.textlength(num_text, font=f_val)
    uw = d.textlength("/100", font=f_unit)
    total_w = nw + 10 + uw
    d.text((cx - total_w / 2, ny2), num_text, font=f_val, fill=BLUE)
    d.text((cx - total_w / 2 + nw + 10, ny2 + 50), "/100", font=f_unit, fill=TEXT_FAINT)

    explain_lines = [
        "Shows where this week ranks vs. the past year of liquidity flow —",
        "0 = most drained, 100 = most flooded.",
    ]
    ey = ny2 + 118
    for line in explain_lines:
        ew = d.textlength(line, font=f_explain)
        d.text((cx - ew / 2, ey), line, font=f_explain, fill=TEXT_FAINT)
        ey += 26

    status = index_data["status"]
    sw = d.textlength(status["text_en"].upper(), font=f_badge)
    badge_w = sw + 56
    by = ey + 42
    d.rounded_rectangle([cx - badge_w / 2, by, cx + badge_w / 2, by + 50], radius=25, fill=status["bg"])
    d.text((cx - sw / 2, by + 12), status["text_en"].upper(), font=f_badge, fill=status["color"])

    # --- 1W/4W/12W/52W change strip, in percentile points (%p) — matches site ---
    strip_y = by + 95
    d.text((pad, strip_y), "Index Change by Window (percentile points)", font=f_label, fill=TEXT_DARK)
    strip_y += 52
    windows = index_data["window_changes"]
    n = len(windows)
    gap = 20
    box_w = (CANVAS_W - 2 * pad - gap * (n - 1)) / n
    for i, wc in enumerate(windows):
        bx = pad + i * (box_w + gap)
        d.rounded_rectangle([bx, strip_y, bx + box_w, strip_y + 118], radius=16,
                             fill=(247, 248, 250), outline=CARD_BORDER, width=2)
        lw = d.textlength(wc["label"], font=f_change_label)
        d.text((bx + box_w / 2 - lw / 2, strip_y + 16), wc["label"], font=f_change_label, fill=TEXT_GRAY)
        if wc["delta_pp"] is None:
            val_text, vcolor = "N/A", TEXT_GRAY
        else:
            val_text = f"{'+' if wc['delta_pp'] > 0 else ''}{wc['delta_pp']}%p"
            vcolor = GREEN_TX if wc["delta_pp"] >= 0 else RED_TX
        vw = d.textlength(val_text, font=f_change_val)
        d.text((bx + box_w / 2 - vw / 2, strip_y + 55), val_text, font=f_change_val, fill=vcolor)

    dy = strip_y + 160
    d.text((pad, dy), "Biggest Drivers This Week", font=f_driver_head, fill=TEXT_DARK)
    dy += 46
    for drv in top_drivers:
        sign_d = "+" if drv["value"] > 0 else ""
        line = f"• {drv['label']}: {sign_d}{drv['value']:.1f} B$/Week"
        d.text((pad, dy), line, font=f_driver, fill=TEXT_BODY)
        dy += 40

    _footer(d, pad, H - 40 - 45, f_footer)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path)
    return out_path


# ---------------------------------------------------------------------------
# Reusable gradient-fill line chart card (Wednesday knowledge, urgent scan,
# and Monday's secondary NETMARKETFLOW trend chart)
# ---------------------------------------------------------------------------
def create_metric_chart_card(
    title: str,
    ticker: str,
    chart_values: List[float],
    chart_dates: List[str],
    unit: str,
    badge_text: Optional[str] = None,
    subtitle: Optional[str] = None,
    site_name: str = "US Liquidity Dashboard",
    out_path: str = "output/metric_chart_card.png",
) -> str:
    """Single-indicator gradient-fill line chart, 'Candidate C' style."""
    H = 1080
    img, d = _new_card(H)
    pad = 70

    f_brand = _font(28, "Bold")
    f_ticker = _font(24, "SemiBold")
    f_title = _font(36, "SemiBold")
    f_subtitle = _font(22, "Regular")
    f_val = _font(72, "ExtraBold")
    f_unit = _font(26, "Medium")
    f_badge = _font(22, "Bold")
    f_axis = _font(19, "Regular")
    f_footer = _font(18, "Regular")

    _header(d, pad, f_brand, f_ticker, ticker, site_name)

    title_lines = _wrap_text(d, title, f_title, CANVAS_W - 2 * pad)
    ty = 150
    for line in title_lines[:2]:
        d.text((pad, ty), line, font=f_title, fill=TEXT_BODY)
        ty += 44

    if subtitle:
        d.text((pad, ty + 4), subtitle, font=f_subtitle, fill=TEXT_FAINT)
        ty += 34

    vy = ty + 15
    if chart_values:
        current = chart_values[-1]
        val_text = f"{current:,.2f}" if unit == "%" else f"{current:,.1f}"
        d.text((pad, vy), val_text, font=f_val, fill=BLUE)
        vw = d.textlength(val_text, font=f_val)
        unit_label = unit if unit == "%" else f" {unit}"
        d.text((pad + vw + 12, vy + 35), unit_label, font=f_unit, fill=TEXT_GRAY)

    if badge_text:
        bw = d.textlength(badge_text, font=f_badge) + 28
        d.rounded_rectangle([CANVAS_W - pad - bw, vy + 15, CANVAS_W - pad, vy + 15 + 42],
                             radius=21, fill=GREEN_BG)
        d.text((CANVAS_W - pad - bw + 14, vy + 25), badge_text, font=f_badge, fill=GREEN_TX)

    cl, cr, ct, cb = pad, CANVAS_W - pad, vy + 120, vy + 120 + 340
    if len(chart_values) >= 2:
        vmin, vmax = min(chart_values), max(chart_values)
        vrange = (vmax - vmin) or 1.0
        n = len(chart_values)
        step = (cr - cl) / (n - 1)
        pts = [(cl + i * step, cb - ((v - vmin) / vrange) * (cb - ct)) for i, v in enumerate(chart_values)]

        area = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ad = ImageDraw.Draw(area)
        ad.polygon(pts + [(cr, cb), (cl, cb)], fill=(37, 99, 235, 55))
        img.paste(Image.alpha_composite(img.convert("RGBA"), area).convert("RGB"))
        d = ImageDraw.Draw(img)

        # v4 addition: the chart previously had NO y-axis scale at all — a
        # reader could see the line move but not what range it moved across,
        # so a 0.39% spread and a 3.5% spread would visually look identical.
        # Print the min/max values actually spanned by the visible line,
        # right-aligned inside the chart area so they don't collide with the
        # line itself. For any series that actually crosses zero (spreads,
        # net-flow) also draw a dashed zero-reference line — the level where
        # e.g. a yield curve flips from normal to inverted is exactly the
        # kind of context a bare line chart otherwise hides.
        def _fmt_axis_val(v: float) -> str:
            return f"{v:,.2f}{unit}" if unit == "%" else f"{v:,.0f}{unit}"

        max_lbl = _fmt_axis_val(vmax)
        min_lbl = _fmt_axis_val(vmin)
        d.text((cl, ct - 4), max_lbl, font=f_axis, fill=TEXT_FAINT)
        d.text((cl, cb - 24), min_lbl, font=f_axis, fill=TEXT_FAINT)

        if vmin < 0 < vmax:
            zero_y = cb - ((0 - vmin) / vrange) * (cb - ct)
            dash_len, gap_len, x = 6, 5, cl
            while x < cr:
                x_end = min(x + dash_len, cr)
                d.line([(x, zero_y), (x_end, zero_y)], fill=TEXT_FAINT, width=1)
                x = x_end + gap_len
            zero_lbl = "0" + (unit if unit == "%" else "")
            d.text((cl, zero_y - 26), zero_lbl, font=f_axis, fill=TEXT_FAINT)

        # v2 addition: week-to-week values (especially diff-based metrics
        # like net liquidity flow) can be genuinely noisy — a raw connected
        # line often just looks like meaningless jagged static. A short
        # rolling-average trend line drawn on top makes the actual direction
        # readable at a glance, while the raw line (now lighter/thinner)
        # stays visible underneath for anyone who wants the exact weekly
        # detail. Skipped for short/near-flat series where it wouldn't add
        # anything (smoothing 8 points is pointless).
        d.line(pts, fill=(163, 191, 250), width=2, joint="curve")

        smooth_window = 4
        if n >= smooth_window * 3:
            smoothed = []
            for i in range(n):
                lo = max(0, i - smooth_window + 1)
                smoothed.append(sum(chart_values[lo:i + 1]) / (i - lo + 1))
            spts = [(cl + i * step, cb - ((v - vmin) / vrange) * (cb - ct)) for i, v in enumerate(smoothed)]
            d.line(spts, fill=BLUE, width=6, joint="curve")
            lx, ly = spts[-1]
        else:
            d.line(pts, fill=BLUE, width=5, joint="curve")
            lx, ly = pts[-1]

        d.ellipse([lx - 8, ly - 8, lx + 8, ly + 8], fill=BLUE, outline="white", width=3)

        d.text((cl, cb + 14), chart_dates[0][5:] if chart_dates else "", font=f_axis, fill=TEXT_FAINT)
        lbl = "Now"
        lw = d.textlength(lbl, font=f_axis)
        d.text((cr - lw, cb + 14), lbl, font=f_axis, fill=TEXT_FAINT)

    weeks_label = f"Last {len(chart_values)} weeks" if chart_values else "Not enough data"
    if len(chart_values) >= 12:
        weeks_label += "  ·  bold line = 4-week trend"
    d.text((pad, cb + 48), weeks_label, font=f_axis, fill=TEXT_FAINT)

    _footer(d, pad, H - 78, f_footer)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path)
    return out_path


# ---------------------------------------------------------------------------
# Tuesday: this month's FRED release calendar
# ---------------------------------------------------------------------------
def create_calendar_card(
    events: List[Dict],
    year: int,
    month: int,
    site_name: str = "US Liquidity Dashboard",
    out_path: str = "output/calendar_card.png",
) -> str:
    """`events` items: {"name": str, "date": date, "is_past": bool}.

    v2: replaced the old long vertical list (unreadable once more than a
    couple events were on the calendar, and gave zero sense of WHEN in the
    month they land) with a real calendar-grid layout: a Mon-Fri grid of the
    current month on the left with event days checked off, and the same
    dates listed with their release name on the right — matching the
    reference layout the user asked for."""
    import calendar as cal_module

    pad = 60
    H = 1040
    img, d = _new_card(H)

    f_brand = _font(28, "Bold")
    f_ticker = _font(24, "SemiBold")
    f_title = _font(42, "ExtraBold")
    f_daylabel = _font(19, "Bold")
    f_daynum = _font(23, "SemiBold")
    f_date = _font(22, "Bold")
    f_name = _font(20, "Regular")
    f_footer = _font(19, "Regular")
    f_empty = _font(24, "Regular")

    _header(d, pad, f_brand, f_ticker, "CALENDAR", site_name)

    month_label = f"{cal_module.month_name[month]} {year}"
    d.text((pad, 148), month_label, font=f_title, fill=TEXT_DARK)
    d.text((pad, 208), "Major US Economic Releases", font=f_name, fill=TEXT_GRAY)

    event_days = {e["date"].day for e in events}

    # --- Left: Mon-Fri grid for the current month -------------------------
    grid_left = pad
    grid_top = 270
    col_w = 78
    row_h = 78
    day_labels = ["MON", "TUE", "WED", "THU", "FRI"]

    for i, lbl in enumerate(day_labels):
        cx = grid_left + i * col_w + col_w / 2
        lw = d.textlength(lbl, font=f_daylabel)
        d.text((cx - lw / 2, grid_top), lbl, font=f_daylabel, fill=TEXT_GRAY)
    d.rectangle([grid_left, grid_top + 30, grid_left + col_w * 5, grid_top + 32], fill=TEXT_DARK)

    cal_module.setfirstweekday(cal_module.MONDAY)
    weeks = cal_module.monthcalendar(year, month)
    row_y = grid_top + 55
    for week in weeks:
        for i in range(5):  # Mon-Fri only — US econ releases never land on weekends
            day_num = week[i]
            cx = grid_left + i * col_w + col_w / 2
            cy = row_y + row_h / 2 - 15
            if day_num == 0:
                d.text((cx - 6, cy), "-", font=f_daynum, fill=TEXT_FAINT)
                continue
            if day_num in event_days:
                d.ellipse([cx - 26, cy - 6, cx + 26, cy + 46], fill=BLUE)
                num_text = str(day_num)
                nw = d.textlength(num_text, font=f_daynum)
                d.text((cx - nw / 2, cy), num_text, font=f_daynum, fill="white")
            else:
                num_text = str(day_num)
                nw = d.textlength(num_text, font=f_daynum)
                d.text((cx - nw / 2, cy), num_text, font=f_daynum, fill=TEXT_BODY)
        row_y += row_h

    grid_bottom = row_y + 10

    # --- Right: date + release name list -----------------------------------
    list_left = grid_left + col_w * 5 + 50
    list_right = CANVAS_W - pad
    ly = grid_top

    if not events:
        d.text((list_left, ly), "No major releases", font=f_empty, fill=TEXT_GRAY)
        d.text((list_left, ly + 34), "on the calendar this month.", font=f_empty, fill=TEXT_GRAY)
    else:
        weekday_abbr = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for e in events[:9]:  # keep the list readable; grid still shows every date
            date_text = e["date"].strftime("%b %d") + f" ({weekday_abbr[e['date'].weekday()]})"
            d.text((list_left, ly), date_text, font=f_date, fill=BLUE)
            ly += 30
            for line in _wrap_text(d, e["name"], f_name, list_right - list_left):
                d.text((list_left, ly), line, font=f_name, fill=TEXT_BODY)
                ly += 27
            ly += 18

    content_bottom = max(grid_bottom, ly)
    _footer(d, pad, content_bottom + 30, f_footer, "Source: FRED Official Release Calendar API")

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.crop((0, 0, CANVAS_W, min(H, content_bottom + 90))).save(out_path)
    return out_path

    _footer(d, pad, H - 60, f_footer, "Source: FRED official Release Calendar API")

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path)
    return out_path


# ---------------------------------------------------------------------------
# Friday: Term of the Day (illustrative icon card — no numeric series)
# ---------------------------------------------------------------------------
def create_term_icon_card(
    term: str,
    definition: str,
    badge: str,
    site_name: str = "US Liquidity Dashboard",
    out_path: str = "output/term_icon_card.png",
) -> str:
    H = 1080
    img, d = _new_card(H)
    pad = 70

    f_brand = _font(28, "Bold")
    f_ticker = _font(24, "SemiBold")
    f_term = _font(42, "ExtraBold")
    f_body = _font(28, "Regular")
    f_footer = _font(19, "Regular")

    _header(d, pad, f_brand, f_ticker, "TERM", site_name)

    # monogram badge inside a soft circle (Inter has no emoji glyphs, so a
    # text monogram is the reliable choice here rather than a pictogram)
    circle_cx, circle_cy, circle_r = CANVAS_W // 2, 330, 130
    d.ellipse([circle_cx - circle_r, circle_cy - circle_r, circle_cx + circle_r, circle_cy + circle_r],
              fill=LIGHTBLUE)
    badge_font_size = 64 if len(badge) <= 4 else (48 if len(badge) <= 6 else 36)
    f_monogram = _font(badge_font_size, "ExtraBold")
    bw = d.textlength(badge, font=f_monogram)
    d.text((circle_cx - bw / 2, circle_cy - badge_font_size / 1.6), badge, font=f_monogram, fill=BLUE)

    term_lines = _wrap_text(d, term, f_term, CANVAS_W - 2 * pad)
    ty = 510
    for line in term_lines[:2]:
        tw = d.textlength(line, font=f_term)
        d.text((circle_cx - tw / 2, ty), line, font=f_term, fill=TEXT_DARK)
        ty += 54

    body_lines = _wrap_text(d, definition, f_body, CANVAS_W - 2 * pad)
    by = ty + 30
    for line in body_lines[:8]:
        d.text((pad, by), line, font=f_body, fill=TEXT_BODY)
        by += 42

    _footer(d, pad, H - 60, f_footer, "US Liquidity Dashboard — Finance Glossary")

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path)
    return out_path


# ---------------------------------------------------------------------------
# Daily news pick — no chart (qualitative story, not a data series), no date
# stamp, no link baked into the image (per design: news posts carry a source-
# name attribution only, never a URL, in either the image or the caption).
# ---------------------------------------------------------------------------
def create_news_card(
    headline: str,
    summary: str,
    impact: str,
    source_name: str,
    site_name: str = "US Liquidity Dashboard",
    out_path: str = "output/news_card.png",
) -> str:
    pad = 70
    f_brand = _font(28, "Bold")
    f_ticker = _font(24, "SemiBold")
    f_headline = _font(40, "ExtraBold")
    f_body = _font(28, "Regular")
    f_label = _font(22, "Bold")
    f_impact = _font(27, "Medium")
    f_footer = _font(19, "Regular")

    # Build on an oversized canvas, then crop to the real content height —
    # headline/summary/impact lengths vary a lot day to day.
    H = 1400
    img, d = _new_card(H)

    _header(d, pad, f_brand, f_ticker, "NEWS", site_name)
    _pill(d, pad, 148, source_name.upper(), f_label, AMBER_TX, AMBER_BG)

    headline_lines = _wrap_text(d, headline, f_headline, CANVAS_W - 2 * pad)
    y = 220
    for line in headline_lines[:4]:
        d.text((pad, y), line, font=f_headline, fill=TEXT_DARK)
        y += 52
    y += 20

    summary_lines = _wrap_text(d, summary, f_body, CANVAS_W - 2 * pad)
    for line in summary_lines[:6]:
        d.text((pad, y), line, font=f_body, fill=TEXT_BODY)
        y += 42
    y += 30

    d.rectangle([pad, y, CANVAS_W - pad, y + 2], fill=LINE_COLOR)  # thin divider
    y += 40

    d.text((pad, y), "EXPECTED IMPACT", font=f_label, fill=BLUE)
    y += 40
    impact_lines = _wrap_text(d, impact, f_impact, CANVAS_W - 2 * pad)
    for line in impact_lines[:6]:
        d.text((pad, y), line, font=f_impact, fill=TEXT_DARK)
        y += 40
    y += 40

    _footer(d, pad, y, f_footer, f"Source: {source_name}")
    y += 50

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.crop((0, 0, CANVAS_W, min(H, y + 40))).save(out_path)
    return out_path
