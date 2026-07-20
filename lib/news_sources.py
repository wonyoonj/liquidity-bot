# -*- coding: utf-8 -*-
"""
RSS source list for the daily liquidity-relevant news pick.

Mix of (a) official government sources — highest trust, zero clickbait risk —
and (b) major financial media outlets, for broader/faster coverage of market-
moving stories the official sources won't publish same-day (e.g. "Fed officials
signal...", market reaction pieces).

IMPORTANT: RSS feed URLs occasionally change or go stale. news_fetcher.py is
built to skip any feed that fails to parse (logs a warning, doesn't crash the
run) — so if one of these goes dead, the pipeline keeps working with whatever
sources are still live. Worth spot-checking this list every few months.
"""

NEWS_SOURCES = [
    # --- Official / primary sources (highest trust) ---
    {"name": "Federal Reserve", "url": "https://www.federalreserve.gov/feeds/press_all.xml", "weight": 3},
    {"name": "Federal Reserve (Monetary Policy)", "url": "https://www.federalreserve.gov/feeds/press_monetary.xml", "weight": 3},
    {"name": "U.S. Treasury", "url": "https://home.treasury.gov/rss/press-releases.xml", "weight": 3},
    {"name": "NY Fed – Liberty Street Economics", "url": "https://libertystreeteconomics.newyorkfed.org/feed/", "weight": 2},

    # --- Major financial media (broader/faster market coverage) ---
    {"name": "CNBC – Economy", "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258", "weight": 2},
    {"name": "MarketWatch – Top Stories", "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories", "weight": 2},
    {"name": "MarketWatch – Real Time Headlines", "url": "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines", "weight": 2},
    {"name": "Investing.com – Economic News", "url": "https://www.investing.com/rss/news_301.rss", "weight": 1},
    {"name": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex", "weight": 1},
]

# Prefilter keywords — an entry must match at least one (case-insensitive) to
# even be considered a liquidity-relevant candidate. Keeps the LLM call cheap
# and focused, and screens out obviously irrelevant stories (earnings of a
# random company, unrelated politics, etc.) before spending an API call.
RELEVANCE_KEYWORDS = [
    "fed ", "federal reserve", "fomc", "powell", "rate cut", "rate hike",
    "interest rate", "basis point", "treasury", "tga", "reverse repo",
    "repo market", "balance sheet", "quantitative tightening", "quantitative easing",
    "qt", "qe", "inflation", "cpi", "pce", "jobs report", "nonfarm payroll",
    "unemployment", "yield", "bond market", "sofr", "money market fund",
    "bank reserves", "liquidity", "money supply", "debt ceiling",
    "government shutdown", "credit market", "dollar index", "dxy",
]
