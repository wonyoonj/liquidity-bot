# -*- coding: utf-8 -*-
"""
Splits long captions into Threads-sized chunks instead of truncating them.

WHY THIS EXISTS: Threads hard-caps a single post at 500 characters. The old
code just did `text[:500]` deep inside lib/post_threads.py — which silently
cut posts off mid-sentence (this is exactly the "...tend to move al" cut-off
the user saw, with Threads' own UI then showing a "1/2" swipe indicator on
top of that). The fix is to count the real character length up front
(spaces included, same as Threads' own counter) and, if a post doesn't fit
in one, split it at clean paragraph/sentence/word boundaries and post the
remainder as chained replies — so nothing is ever silently cut off.
"""
from __future__ import annotations

from typing import List

# Threads' real limit is 500. Leaving a small margin below that (rather than
# splitting at exactly 500) avoids off-by-one edge cases from counting
# differences between Python's len() and Threads' own counter.
THREADS_CHAR_LIMIT = 480


def split_text_by_length(text: str, limit: int = THREADS_CHAR_LIMIT) -> List[str]:
    """Splits `text` into chunks of at most `limit` characters each (counted
    with plain len() — i.e. every character including spaces/newlines,
    matching how Threads itself counts). Breaks at the best available
    boundary before the limit — paragraph break, then sentence end, then a
    plain space — so a chunk never ends mid-word. Falls back to a hard cut
    only if no such boundary exists in a reasonable window (extremely long
    single "word", e.g. a URL).

    Returns [] for empty input, [text] unchanged if it already fits."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    chunks: List[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]

        cut = window.rfind("\n\n")
        if cut < limit * 0.4:
            sentence_cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
            cut = sentence_cut + 1 if sentence_cut >= limit * 0.4 else cut
        if cut < limit * 0.4:
            space_cut = window.rfind(" ")
            cut = space_cut if space_cut >= limit * 0.3 else cut
        if cut < limit * 0.3:
            cut = limit  # last resort: nothing to break on, hard-cut

        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()

    if remaining:
        chunks.append(remaining)
    return chunks
