# -*- coding: utf-8 -*-
"""
Python re-implementation of the "Market Total Net Liquidity Supply" formula
used on the website (index.html -> updateLiquidityFlowAnimation()).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict

Series = List[Tuple[datetime, float]]


def _closest(data: Series, target_date: datetime) -> Optional[float]:
    if not data:
        return None
    closest_val = data[-1][1]
    min_diff = abs(data[-1][0] - target_date)
    for date, value in reversed(data[:-1]):
        diff = abs(date - target_date)
        if diff < min_diff:
            min_diff = diff
            closest_val = value
        else:
            break
    return closest_val


def compute_net_market_flow(data_store: dict, as_of: Optional[datetime] = None) -> dict:
    required = ["WTREGEN", "WALCL", "RRPONTSYD", "WRESBAL",
                "MMF2MARKET", "MMF2GOVERNMENT", "MMMFFAQ027S"]
    for key in required:
        if not data_store.get(key):
            raise ValueError(f"'{key}' series is empty.")

    if as_of is None:
        common_latest = min(data_store[k][-1][0] for k in
                             ["WTREGEN", "WALCL", "RRPONTSYD", "WRESBAL"])
    else:
        common_latest = as_of

    past_7 = common_latest - timedelta(days=7)
    past_30 = common_latest - timedelta(days=30)

    tga_now = _closest(data_store["WTREGEN"], common_latest)
    tga_past = _closest(data_store["WTREGEN"], past_7)
    walcl_now = _closest(data_store["WALCL"], common_latest)
    walcl_past = _closest(data_store["WALCL"], past_7)
    rrp_now = _closest(data_store["RRPONTSYD"], common_latest)
    rrp_past = _closest(data_store["RRPONTSYD"], past_7)
    resbal_now = _closest(data_store["WRESBAL"], common_latest)
    resbal_past = _closest(data_store["WRESBAL"], past_7)

    if None in (tga_now, tga_past, walcl_now, walcl_past, rrp_now, rrp_past, resbal_now, resbal_past):
        raise ValueError("Not enough TGA/WALCL/RRP/WRESBAL data to compute this metric.")

    tga_diff = (tga_now / 1000) - (tga_past / 1000)
    walcl_diff = (walcl_now / 1000) - (walcl_past / 1000)
    rrp_diff = rrp_now - rrp_past
    resbal_diff = (resbal_now / 1000) - (resbal_past / 1000)
    fed_liquidity_diff = walcl_diff - (tga_diff + 2 * rrp_diff + 2 * resbal_diff)

    latest_date_m = data_store["MMF2MARKET"][-1][0]
    past_date_m = latest_date_m - timedelta(days=30)
    latest_m = _closest(data_store["MMF2MARKET"], latest_date_m)
    past_m = _closest(data_store["MMF2MARKET"], past_date_m)

    latest_date_g = data_store["MMF2GOVERNMENT"][-1][0]
    past_date_g = latest_date_g - timedelta(days=30)
    latest_g = _closest(data_store["MMF2GOVERNMENT"], latest_date_g)
    past_g = _closest(data_store["MMF2GOVERNMENT"], past_date_g)

    if None in (latest_m, past_m, latest_g, past_g):
        raise ValueError("Not enough MMF2MARKET/MMF2GOVERNMENT data to compute this metric.")
    mmf_to_market_combined = ((latest_m - past_m) + (latest_g - past_g)) / 1e9

    latest_date_t = data_store["MMMFFAQ027S"][-1][0]
    past_date_t = latest_date_t - timedelta(days=30)
    latest_t = _closest(data_store["MMMFFAQ027S"], latest_date_t)
    past_t = _closest(data_store["MMMFFAQ027S"], past_date_t)
    if None in (latest_t, past_t):
        raise ValueError("Not enough MMMFFAQ027S data to compute this metric.")
    mmf_asset_change = (latest_t - past_t) / 1e9

    final_mmf_to_market_diff = (mmf_to_market_combined - mmf_asset_change) / 4.0
    net_market_flow = fed_liquidity_diff - tga_diff + final_mmf_to_market_diff

    return {
        "as_of_date": common_latest.strftime("%Y-%m-%d"),
        "tga_diff": round(tga_diff, 2),
        "fed_liquidity_diff": round(fed_liquidity_diff, 2),
        "final_mmf_to_market_diff": round(final_mmf_to_market_diff, 2),
        "net_market_flow": round(net_market_flow, 2),
    }


def classify_state(net_market_flow: float) -> dict:
    if net_market_flow >= 50:
        return {"level": "strong-supply", "color": (25, 135, 84),
                "emoji": "🟢", "text_ko": "강한 유동성 공급 국면", "text_en": "Strong Liquidity Supply"}
    if net_market_flow > 0:
        return {"level": "supply", "color": (255, 193, 7),
                "emoji": "🟡", "text_ko": "완만한 유동성 공급 국면", "text_en": "Mild Liquidity Supply"}
    if net_market_flow > -50:
        return {"level": "drain", "color": (253, 126, 20),
                "emoji": "🟠", "text_ko": "완만한 유동성 흡수 국면", "text_en": "Mild Liquidity Drain"}
    return {"level": "strong-drain", "color": (220, 53, 69),
            "emoji": "🔴", "text_ko": "강한 유동성 흡수 국면", "text_en": "Strong Liquidity Drain"}


def compute_trend_text(data_store: dict, current_result: dict) -> str:
    try:
        as_of = datetime.strptime(current_result["as_of_date"], "%Y-%m-%d")
        month_ago_result = compute_net_market_flow(data_store, as_of=as_of - timedelta(days=28))
        diff = current_result["net_market_flow"] - month_ago_result["net_market_flow"]
        if abs(diff) <= 5:
            return ""
        return " · Faster supply pace than a month ago" if diff > 0 else " · Slower supply pace than a month ago"
    except Exception:
        return ""


def compute_net_market_flow_history(data_store: dict, weeks: int = 12) -> List[Dict]:
    """Walk back week-by-week from the latest common date and compute net_market_flow
    for each point. Used for the Friday recap chart and Sunday 'record' content."""
    base_dates = sorted({d for d, _ in data_store.get("WTREGEN", [])})
    if not base_dates:
        return []
    latest = base_dates[-1]

    results: List[Dict] = []
    seen_dates = set()
    for i in range(weeks):
        as_of = latest - timedelta(weeks=i)
        try:
            r = compute_net_market_flow(data_store, as_of=as_of)
        except Exception:
            continue
        if r["as_of_date"] in seen_dates:
            continue
        seen_dates.add(r["as_of_date"])
        results.append(r)

    results.sort(key=lambda r: r["as_of_date"])
    return results
