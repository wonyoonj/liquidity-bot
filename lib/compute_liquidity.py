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


INDEX_WINDOWS = [("1W", 1), ("4W", 4), ("12W", 12), ("52W", 52)]  # matches the site exactly


def compute_liquidity_index(data_store: dict, lookback_weeks: int = 260) -> Dict:
    """Re-implements the site's actual 'LIQUIDITY INDEX' gauge (index.html ->
    renderLiquidityIndexGauge()): the current net_market_flow value's
    PERCENTILE RANK against its own historical distribution, 0-100.
    0 = most drained week on record (site label: UNDERSUPPLY),
    100 = most flooded week on record (site label: FLOODED).
    This is NOT a linear mapping of dollar value — it's rank-based, exactly
    matching what a viewer sees on the live dashboard gauge."""
    history = compute_net_market_flow_history(data_store, weeks=lookback_weeks)
    if len(history) < 10:
        raise ValueError("Not enough history to compute a percentile-based Liquidity Index.")

    sorted_history = sorted(history, key=lambda h: h["as_of_date"])
    values_sorted = sorted(h["net_market_flow"] for h in sorted_history)
    latest = sorted_history[-1]
    latest_val = latest["net_market_flow"]

    def _percentile_of(v: float) -> int:
        rank = sum(1 for x in values_sorted if x <= v)
        return max(0, min(100, round((rank / len(values_sorted)) * 100)))

    percentile = _percentile_of(latest_val)

    if percentile >= 70:
        status = {"text_en": "Liquidity Expansion", "color": (192, 57, 43), "bg": (253, 236, 236)}
    elif percentile <= 30:
        status = {"text_en": "Liquidity Contraction", "color": (28, 111, 214), "bg": (233, 242, 254)}
    else:
        status = {"text_en": "Neutral", "color": (184, 134, 11), "bg": (255, 243, 214)}

    # 1W/4W/12W/52W change in percentile POINTS (%p) — matches site exactly.
    window_changes = []
    dated = [(datetime.strptime(h["as_of_date"], "%Y-%m-%d"), h["net_market_flow"]) for h in sorted_history]
    latest_date = dated[-1][0]
    for label, weeks in INDEX_WINDOWS:
        target_date = latest_date - timedelta(weeks=weeks)
        closest = min(dated[:-1], key=lambda dv: abs(dv[0] - target_date), default=None) if len(dated) > 1 else None
        if closest is None:
            window_changes.append({"label": label, "delta_pp": None})
            continue
        past_percentile = _percentile_of(closest[1])
        window_changes.append({"label": label, "delta_pp": percentile - past_percentile})

    return {
        "percentile": percentile,
        "latest_value": round(latest_val, 1),
        "as_of_date": latest["as_of_date"],
        "status": status,
        "window_changes": window_changes,
    }


GAUGE_MIN = -150.0   # legacy linear gauge bounds — kept for compute_gauge_angle() below
GAUGE_MAX = 150.0

# Windows previously used for the linear % readout — superseded by
# compute_liquidity_index()'s INDEX_WINDOWS (percentile points), kept here
# only in case compute_window_changes() is still used elsewhere.
CHANGE_WINDOWS = [("1W", 1), ("4W", 4), ("13W", 13), ("26W", 26), ("52W", 52)]


def compute_gauge_angle(net_market_flow: float) -> float:
    """Maps net_market_flow to a -90..+90 degree needle angle (like the site's
    speedometer widget), clamped at the extremes."""
    clamped = max(GAUGE_MIN, min(GAUGE_MAX, net_market_flow))
    fraction = (clamped - GAUGE_MIN) / (GAUGE_MAX - GAUGE_MIN)  # 0..1
    return -90.0 + fraction * 180.0


def compute_window_changes(data_store: dict) -> List[Dict]:
    """For each window in CHANGE_WINDOWS, compares the sum of net_market_flow
    over the trailing N weeks to the N weeks immediately before that, and
    expresses it as a % change — i.e. 'is liquidity supply pace speeding up
    or slowing down' over each horizon (1W/4W/13W/26W/52W), mirroring the
    site's multi-window % change readout."""
    history = compute_net_market_flow_history(data_store, weeks=105)  # enough for a 52W-vs-prior-52W compare
    values = [h["net_market_flow"] for h in history]

    results = []
    for label, n in CHANGE_WINDOWS:
        if len(values) < n * 2:
            results.append({"label": label, "pct": None})
            continue
        recent_sum = sum(values[-n:])
        prior_sum = sum(values[-2 * n:-n])
        if abs(prior_sum) < 1e-6:
            pct = None
        else:
            pct = (recent_sum - prior_sum) / abs(prior_sum) * 100.0
        results.append({"label": label, "pct": round(pct, 1) if pct is not None else None})
    return results


def compute_top_drivers(result: dict, top_n: int = 2) -> List[Dict]:
    """Returns the top_n biggest contributors to this week's net_market_flow,
    each with a plain-language label and its signed B$/Week contribution —
    used for the Monday 'why is liquidity like this' explanation."""
    contributions = {
        "Treasury's TGA balance": -result["tga_diff"],
        "the Fed's balance sheet / bank reserves": result["fed_liquidity_diff"],
        "Money Market Fund flows": result["final_mmf_to_market_diff"],
    }
    ranked = sorted(contributions.items(), key=lambda kv: abs(kv[1]), reverse=True)
    return [{"label": label, "value": round(val, 1)} for label, val in ranked[:top_n]]


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
