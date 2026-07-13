# -*- coding: utf-8 -*-
"""
Saturday content: a rotating "Term of the Day" glossary covering the
indicators used across the site. No external API needed — pure static data,
picked deterministically by day-of-year so it cycles predictably.
"""
from __future__ import annotations

from datetime import date
from typing import Dict

TERMS = [
    {
        "term": "TGA (Treasury General Account)",
        "definition": (
            "The US Treasury's main checking account at the Fed. When the TGA balance "
            "falls, the government is spending faster than it's collecting/borrowing — "
            "effectively injecting dollars into the market. A rising TGA does the opposite."
        ),
    },
    {
        "term": "RRP (Overnight Reverse Repo)",
        "definition": (
            "A Fed facility where money market funds park excess cash overnight in "
            "exchange for Treasury collateral. Falling RRP balances mean that cash is "
            "flowing back out into the market (supply); rising RRP means cash is being "
            "parked at the Fed (drain)."
        ),
    },
    {
        "term": "SOFR (Secured Overnight Financing Rate)",
        "definition": (
            "The benchmark overnight rate for loans collateralized by Treasuries. It's "
            "the successor to LIBOR and a key gauge of short-term funding market stress."
        ),
    },
    {
        "term": "EFFR (Effective Federal Funds Rate)",
        "definition": (
            "The actual (unsecured) rate banks charge each other for overnight loans of "
            "reserves. The Fed targets a range for this rate as its primary policy tool."
        ),
    },
    {
        "term": "SOFR-EFFR Spread",
        "definition": (
            "The gap between the secured (SOFR) and unsecured (EFFR) overnight rates. "
            "A widening spread often signals stress or reduced liquidity in short-term "
            "funding markets."
        ),
    },
    {
        "term": "WALCL (Fed Total Assets)",
        "definition": (
            "The size of the Federal Reserve's balance sheet. It expands during "
            "Quantitative Easing (QE) and shrinks during Quantitative Tightening (QT), "
            "directly affecting the amount of liquidity in the financial system."
        ),
    },
    {
        "term": "WRESBAL (Reserve Balances)",
        "definition": (
            "Cash reserves that commercial banks hold at the Fed. These reserves are the "
            "base layer of banking system liquidity — low reserves can tighten short-term "
            "funding conditions."
        ),
    },
    {
        "term": "MMF (Money Market Funds)",
        "definition": (
            "Low-risk mutual funds that invest in short-term instruments (Treasuries, repo, "
            "commercial paper). Where MMFs choose to park their money — at the Fed's RRP "
            "facility vs. in the open market — is a useful signal of liquidity direction."
        ),
    },
    {
        "term": "QE vs. QT",
        "definition": (
            "Quantitative Easing (QE): the Fed buys bonds to expand its balance sheet and "
            "add liquidity. Quantitative Tightening (QT): the Fed lets bonds mature without "
            "reinvesting, shrinking its balance sheet and draining liquidity."
        ),
    },
    {
        "term": "CPI vs. PCE",
        "definition": (
            "Both measure inflation, but differ in methodology. CPI (Bureau of Labor "
            "Statistics) tracks a fixed basket of goods urban consumers buy. PCE (Bureau of "
            "Economic Analysis) adjusts for substitution effects and is the Fed's preferred "
            "inflation gauge for setting policy."
        ),
    },
    {
        "term": "FOMC (Federal Open Market Committee)",
        "definition": (
            "The Fed's policy-setting committee that meets roughly every six weeks to "
            "decide the federal funds rate target and other monetary policy tools."
        ),
    },
    {
        "term": "Discount Rate",
        "definition": (
            "The interest rate the Fed charges commercial banks for short-term loans "
            "through its discount window — a backstop source of liquidity for banks."
        ),
    },
    {
        "term": "IORB (Interest on Reserve Balances)",
        "definition": (
            "The rate the Fed pays banks on reserves held at the Fed. It acts as a floor "
            "that helps keep the effective federal funds rate within the Fed's target range."
        ),
    },
    {
        "term": "Yield Curve (10Y-2Y / 10Y-3M Spread)",
        "definition": (
            "The gap between long- and short-term Treasury yields. When short-term yields "
            "exceed long-term yields (inversion), it has historically been one of the most "
            "watched recession warning signals."
        ),
    },
    {
        "term": "Net Market Liquidity Flow",
        "definition": (
            "This site's core metric: the net weekly dollar amount actually flowing into "
            "the market through the Fed, Treasury (TGA), and Money Market Funds combined. "
            "Positive = liquidity supply. Negative = liquidity drain."
        ),
    },
]


def get_term_of_the_day(d: date | None = None) -> Dict[str, str]:
    """Deterministic rotation based on day-of-year, so the same date always
    yields the same term (useful for testing) and the cycle repeats every
    len(TERMS) days rather than randomly."""
    d = d or date.today()
    idx = d.timetuple().tm_yday % len(TERMS)
    return TERMS[idx]


def format_term_caption(term_entry: Dict[str, str], site_url: str) -> str:
    return (
        f"📖 <b>Term of the Day: {term_entry['term']}</b>\n\n"
        f"{term_entry['definition']}\n\n"
        f"👉 See it in the live dashboard: {site_url}\n"
        f"#USLiquidity #FinanceGlossary #LearnFinance"
    )
