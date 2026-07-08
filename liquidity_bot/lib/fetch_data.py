# -*- coding: utf-8 -*-
"""
사이트(원뎅이의 미국 유동성 현황)가 이미 사용 중인 Netlify 서버리스 함수에서
FRED/OFR 데이터를 그대로 가져오는 모듈입니다.

웹사이트 JS 코드의 아래 부분과 완전히 동일한 데이터 소스를 사용합니다.
    const FUNCTION_BASE_URL = '/.netlify/functions/get-csv-data';
    const functionUrl = `${FUNCTION_BASE_URL}?indicator=${indicator}`;

이렇게 하면 파이썬에서 계산한 값과 웹사이트에 표시되는 값이 100% 일치합니다.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import List, Tuple

import requests

# 실제 배포된 도메인으로 바꿔주세요. (예: https://americayoudongsung.netlify.app)
SITE_API_BASE = os.environ.get(
    "SITE_API_BASE",
    "https://americayoudongsung.netlify.app",
)
ENDPOINT_PATH = "/.netlify/functions/get-csv-data"

REQUIRED_INDICATORS = [
    "WTREGEN",        # 정부 TGA 잔고
    "WALCL",          # 연준 총자산
    "RRPONTSYD",      # 역레포 잔고
    "WRESBAL",        # 지급준비금
    "MMF2MARKET",     # MMF -> 시장(민간)
    "MMF2GOVERNMENT",  # MMF -> 정부채권
    "MMMFFAQ027S",    # MMF 전체 자산
]


class FetchError(RuntimeError):
    pass


def _parse_csv(text: str) -> List[Tuple[datetime, float]]:
    """웹사이트의 parseCSV() 함수와 동일한 파싱 규칙."""
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
    """단일 지표를 CSV로 받아 [(date, value), ...] 형태로 반환."""
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


def fetch_all() -> dict:
    """필요한 지표 7개를 모두 가져와 dict로 반환합니다."""
    data_store = {}
    for indicator in REQUIRED_INDICATORS:
        data_store[indicator] = fetch_indicator(indicator)
    return data_store
