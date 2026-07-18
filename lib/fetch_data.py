# -*- coding: utf-8 -*-
"""
사이트(원뎅이의 미국 유동성 현황)가 이미 사용 중인 Netlify 서버리스 함수에서
FRED/OFR 데이터를 그대로 가져오는 모듈입니다.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import List, Tuple

import requests

SITE_API_BASE = os.environ.get(
    "SITE_API_BASE",
    "https://americayoudongsung.netlify.app",
)
ENDPOINT_PATH = "/.netlify/functions/get-csv-data"

REQUIRED_INDICATORS = [
    "WTREGEN", "WALCL", "RRPONTSYD", "WRESBAL",
    "MMF2MARKET", "MMF2GOVERNMENT", "MMMFFAQ027S",
]

# Rate indicators shown on the site's "금리" (rates) page — CONFIRMED against
# the actual csvfile/ listing in the user's fred-data GitHub repo (checked
# July 2026). These are the real indicator codes the site's own
# get-csv-data function supports; fetch_all() will still skip any that ever
# go missing without breaking the pipeline.
# NOTE: the site does NOT have a raw T10Y2Y series — the 10Y-2Y spread and
# SOFR-EFFR / SOFR-IORB spreads are computed CLIENT-SIDE on the site from
# DGS10/DGS2/SOFR/FEDFUNDS/IORB. Our bot mirrors that: see
# lib/signal_scanner.py's DERIVED_SPREAD_TARGETS and
# lib/knowledge_content.py's derived YIELD_SPREAD topic, both computed from
# the raw series below rather than fetched directly.
OPTIONAL_RATE_INDICATORS = [
    "FEDFUNDS",  # EFFR — Effective Federal Funds Rate
    "SOFR",      # Secured Overnight Financing Rate
    "IORB",      # Interest on Reserve Balances
    "DPCREDIT",  # Fed discount window primary credit rate
    "DGS3MO",    # 3-Month Treasury yield
    "DGS2",      # 2-Year Treasury yield
    "DGS10",     # 10-Year Treasury yield
    "RRPONTSYAWARD",  # RRP award rate
]


class FetchError(RuntimeError):
    pass


def _parse_csv(text: str) -> List[Tuple[datetime, float]]:
    lines = [line for line in text.strip().splitlines() if line.strip() != ""]
    if len(lines) <= 1:
        return []

    headers = [h.strip() for h in lines[0].split(",")]
    date_idx = next(
        (i for i, h in enumerate(headers) if h.lower() in ("date", "data")), -1
    )
    if date_idx == -1:
        return []
    value_idx = next((i for i in range(len(headers)) if i != date_idx), -1)
    if value_idx == -1:
        return []

    parsed: List[Tuple[datetime, float]] = []
    for line in lines[1:]:
        cols = line.split(",")
        if len(cols) <= max(date_idx, value_idx):
            continue
        date_str = cols[date_idx].strip()
        value_str = cols[value_idx].strip()
        if value_str in ("", "."):
            continue
        try:
            date_obj = datetime.fromisoformat(date_str[:10])
            value_num = float(value_str)
        except ValueError:
            continue
        parsed.append((date_obj, value_num))

    parsed.sort(key=lambda x: x[0])
    return parsed


def fetch_indicator(indicator: str, timeout: int = 20) -> List[Tuple[datetime, float]]:
    url = f"{SITE_API_BASE}{ENDPOINT_PATH}"
    try:
        resp = requests.get(url, params={"indicator": indicator}, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise FetchError(f"'{indicator}' 데이터를 가져오지 못했습니다: {e}") from e

    data = _parse_csv(resp.text)
    if not data:
        raise FetchError(f"'{indicator}' 응답에 유효한 데이터가 없습니다.")
    return data


def fetch_all(include_rates: bool = True) -> dict:
    data_store = {}
    for indicator in REQUIRED_INDICATORS:
        data_store[indicator] = fetch_indicator(indicator)

    if include_rates:
        for indicator in OPTIONAL_RATE_INDICATORS:
            try:
                data_store[indicator] = fetch_indicator(indicator)
            except FetchError as e:
                # Optional — a missing/unsupported rate series should never
                # break the core liquidity pipeline.
                print(f"[fetch_data] Optional rate series '{indicator}' unavailable, skipping: {e}")

    return data_store
