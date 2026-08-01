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

# Single dedicated source for the "Daily Top 4 Headlines" feature
# (see daily_top4.py / lib/top4_fetcher.py). Kept separate from NEWS_SOURCES
# below (which is a multi-source, keyword-prefiltered list feeding
# daily_news.py's single-story picker) because this feature has a
# different shape: exactly one trusted wire source, no keyword prefilter
# needed since the feed itself is already scoped to business/finance, and
# "today" means the US/Eastern calendar date rather than a rolling window.
#
# NOTE: Reuters retired its old public syndication feed
# (reutersagency.com/feed/?best-topics=...) — it now 404s. reuters.com
# itself does not publish an official public RSS feed either (Reuters news
# is distributed commercially via LSEG). The standard workaround, used
# widely since Reuters dropped public RSS, is a Google News RSS search
# scoped to reuters.com via `site:` — this returns ONLY reuters.com
# articles (real Reuters reporting, Reuters byline/attribution preserved),
# just delivered through Google News' still-public RSS endpoint instead of
# a dead Reuters-hosted one. `when:2d` keeps the pool to the last two days;
# fetch_today_entries() below still does its own precise US/Eastern
# "today" filtering (plus a 36h fallback) on top of this.
REUTERS_TOP4_FEED_URL = (
    "https://news.google.com/rss/search?q=site%3Areuters.com+"
    "(business+OR+markets+OR+economy+OR+finance+OR+earnings)+when%3A2d"
    "&hl=en-US&gl=US&ceid=US:en"
)

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
