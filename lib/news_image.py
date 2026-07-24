# -*- coding: utf-8 -*-
"""
Finds and downloads a real photo for the daily news card, per explicit
request: the news card should show the article's own lead image (or a
clean placeholder if none can be found) instead of a text-only card.

Two-step lookup, cheapest first:
    1. RSS-level image — most feeds already carry a thumbnail/enclosure
       (media:thumbnail, media:content, or an <enclosure type="image/*">)
       right in the entry, no extra HTTP request needed.
    2. og:image fallback — if the feed entry has no image field, fetch the
       article page itself and read its Open Graph og:image meta tag
       (virtually every modern news site sets this for link-preview
       purposes, whether or not it also puts an image in the RSS feed).

Never raises — every function degrades to None on any failure (missing
field, network error, non-image content-type, oversized file, etc.), so a
bad image never breaks the whole daily news post; callers fall back to
generate_card.py's built-in placeholder panel.
"""
from __future__ import annotations

import os
import re
import requests

MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8MB safety cap
_REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; USLiquidityDashboardBot/1.0)"}


def extract_feed_image_url(entry: dict) -> "str | None":
    """Pulls an image URL straight out of a feedparser entry dict, checking
    the fields real-world RSS/Atom feeds actually use, in order of how
    reliably they tend to point at a real lead photo (media:thumbnail and
    media:content are purpose-built for this; enclosures and links are a
    broader fallback)."""
    media_thumbnail = entry.get("media_thumbnail")
    if media_thumbnail and isinstance(media_thumbnail, list):
        url = media_thumbnail[0].get("url")
        if url:
            return url

    media_content = entry.get("media_content")
    if media_content and isinstance(media_content, list):
        for item in media_content:
            url = item.get("url")
            medium = (item.get("medium") or "").lower()
            item_type = (item.get("type") or "").lower()
            if url and (medium == "image" or item_type.startswith("image")):
                return url

    for link in entry.get("links", []) or []:
        if link.get("rel") == "enclosure" and (link.get("type") or "").startswith("image"):
            href = link.get("href")
            if href:
                return href

    return None


def fetch_og_image(article_url: str, timeout: int = 8) -> "str | None":
    """Fetches `article_url` and pulls the og:image (falling back to
    twitter:image) meta tag content. Only reads the first ~200KB of HTML —
    og/twitter meta tags always live in <head>, so there is never a need to
    download an entire page just to find them."""
    if not article_url:
        return None
    try:
        resp = requests.get(article_url, headers=_REQUEST_HEADERS, timeout=timeout, stream=True)
        resp.raise_for_status()
        html_chunk = b""
        for chunk in resp.iter_content(8192):
            html_chunk += chunk
            if len(html_chunk) >= 200_000:
                break
        html = html_chunk.decode("utf-8", errors="ignore")
    except Exception as e:  # noqa: BLE001
        print(f"[news_image] og:image fetch failed for {article_url}: {e}")
        return None

    for prop in ("og:image", "twitter:image"):
        m = re.search(
            rf'<meta[^>]+(?:property|name)=["\']{prop}["\'][^>]+content=["\']([^"\']+)["\']',
            html, re.IGNORECASE,
        )
        if m:
            return m.group(1)
    return None


def download_image(url: str, out_path: str, timeout: int = 10) -> "str | None":
    """Downloads `url` to `out_path`, returning the path on success or None
    on any failure (bad content-type, oversized, network error, etc.)."""
    if not url:
        return None
    try:
        resp = requests.get(url, headers=_REQUEST_HEADERS, timeout=timeout, stream=True)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if not content_type.startswith("image/"):
            print(f"[news_image] Skipping non-image content-type '{content_type}' at {url}")
            return None

        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        total = 0
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(65536):
                total += len(chunk)
                if total > MAX_IMAGE_BYTES:
                    print(f"[news_image] Image at {url} exceeded {MAX_IMAGE_BYTES} bytes, aborting.")
                    f.close()
                    os.remove(out_path)
                    return None
                f.write(chunk)
        return out_path
    except Exception as e:  # noqa: BLE001
        print(f"[news_image] Download failed for {url}: {e}")
        return None


def get_news_photo(entry_raw: dict, article_url: str, out_path: str) -> "str | None":
    """One-call convenience: try the RSS entry's own image field first,
    then fall back to the article page's og:image, download whichever is
    found, and return the local path — or None if no usable image turned
    up anywhere (caller then uses generate_card.py's placeholder panel)."""
    image_url = extract_feed_image_url(entry_raw) or fetch_og_image(article_url)
    if not image_url:
        return None
    return download_image(image_url, out_path)
