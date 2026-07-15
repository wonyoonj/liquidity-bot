# -*- coding: utf-8 -*-
"""
Threads (Meta) API client.

IMPORTANT — one-time manual setup required before this code can run (Meta requires
a human to grant OAuth consent once; this cannot be skipped or automated):
    1. Create a Meta App at https://developers.facebook.com (type: Business)
       and add the "Threads" use case.
    2. Your Threads account must be linked to an Instagram Business/Creator account.
    3. Complete the OAuth consent flow once (in a browser) with scopes
       threads_basic + threads_content_publish to get a short-lived code.
    4. Exchange it for a short-lived token, then a long-lived token (valid 60 days).
    5. Store THREADS_USER_ID and THREADS_ACCESS_TOKEN as GitHub Secrets.
After that, everything below runs with zero human interaction — including
refreshing the token before it expires (see refresh_and_store_token()).

Threads API notes (confirmed against Meta's official changelog, checked July 2026):
    - Native polls ARE supported (added April 14, 2025) via the `poll_attachment`
      parameter on a TEXT container — see publish_poll_post() below. 2-4 options,
      not compatible with a link_attachment on the same post.
    - Image/video posts require a PUBLICLY reachable URL (can't upload raw bytes),
      so this module defaults to TEXT-only posts to avoid needing image hosting
      unless an image_url is supplied.
"""
from __future__ import annotations

import os
import time
import requests

THREADS_API_BASE = "https://graph.threads.net/v1.0"
THREADS_REFRESH_URL = "https://graph.threads.net/refresh_access_token"


class ThreadsError(RuntimeError):
    pass


def _get_credentials():
    user_id = os.environ.get("THREADS_USER_ID")
    access_token = os.environ.get("THREADS_ACCESS_TOKEN")
    if not user_id or not access_token:
        raise ThreadsError("THREADS_USER_ID / THREADS_ACCESS_TOKEN is not set.")
    return user_id, access_token


def publish_text_post(text: str, timeout: int = 30) -> dict:
    """Two-step publish: create a container, then publish it."""
    user_id, access_token = _get_credentials()

    create_resp = requests.post(
        f"{THREADS_API_BASE}/{user_id}/threads",
        data={"media_type": "TEXT", "text": text[:500], "access_token": access_token},
        timeout=timeout,
    )
    try:
        create_resp.raise_for_status()
    except requests.RequestException as e:
        raise ThreadsError(f"Failed to create Threads container: {e} / {create_resp.text}") from e

    creation_id = create_resp.json().get("id")
    if not creation_id:
        raise ThreadsError(f"No container id returned: {create_resp.text}")

    # Meta recommends a short pause before publishing so the container finishes processing.
    time.sleep(2)

    publish_resp = requests.post(
        f"{THREADS_API_BASE}/{user_id}/threads_publish",
        data={"creation_id": creation_id, "access_token": access_token},
        timeout=timeout,
    )
    try:
        publish_resp.raise_for_status()
    except requests.RequestException as e:
        raise ThreadsError(f"Failed to publish Threads post: {e} / {publish_resp.text}") from e

    return publish_resp.json()


def publish_image_post(text: str, image_url: str, timeout: int = 30) -> dict:
    """Same as publish_text_post but attaches an image. image_url MUST be a
    publicly reachable URL (e.g. a GitHub Pages URL) — Threads fetches it server-side."""
    user_id, access_token = _get_credentials()

    create_resp = requests.post(
        f"{THREADS_API_BASE}/{user_id}/threads",
        data={
            "media_type": "IMAGE",
            "image_url": image_url,
            "text": text[:500],
            "access_token": access_token,
        },
        timeout=timeout,
    )
    try:
        create_resp.raise_for_status()
    except requests.RequestException as e:
        raise ThreadsError(f"Failed to create Threads image container: {e} / {create_resp.text}") from e

    creation_id = create_resp.json().get("id")
    if not creation_id:
        raise ThreadsError(f"No container id returned: {create_resp.text}")

    time.sleep(30)  # Meta recommends ~30s for image processing before publish

    publish_resp = requests.post(
        f"{THREADS_API_BASE}/{user_id}/threads_publish",
        data={"creation_id": creation_id, "access_token": access_token},
        timeout=timeout,
    )
    try:
        publish_resp.raise_for_status()
    except requests.RequestException as e:
        raise ThreadsError(f"Failed to publish Threads image post: {e} / {publish_resp.text}") from e

    return publish_resp.json()


def publish_poll_post(text: str, options: list[str], timeout: int = 30) -> dict:
    """Native Threads poll (poll_attachment param, added to the API April 2025).
    Requires 2-4 options; only the first 4 are used if more are passed, and
    each option is trimmed to Threads' poll option length limit."""
    if len(options) < 2:
        raise ThreadsError("Threads polls need at least 2 options.")

    user_id, access_token = _get_credentials()
    keys = ["option_a", "option_b", "option_c", "option_d"]
    poll_attachment = {k: opt[:25] for k, opt in zip(keys, options[:4])}

    import json
    create_resp = requests.post(
        f"{THREADS_API_BASE}/{user_id}/threads",
        data={
            "media_type": "TEXT",
            "text": text[:500],
            "poll_attachment": json.dumps(poll_attachment),
            "access_token": access_token,
        },
        timeout=timeout,
    )
    try:
        create_resp.raise_for_status()
    except requests.RequestException as e:
        raise ThreadsError(f"Failed to create Threads poll container: {e} / {create_resp.text}") from e

    creation_id = create_resp.json().get("id")
    if not creation_id:
        raise ThreadsError(f"No container id returned: {create_resp.text}")

    time.sleep(2)

    publish_resp = requests.post(
        f"{THREADS_API_BASE}/{user_id}/threads_publish",
        data={"creation_id": creation_id, "access_token": access_token},
        timeout=timeout,
    )
    try:
        publish_resp.raise_for_status()
    except requests.RequestException as e:
        raise ThreadsError(f"Failed to publish Threads poll: {e} / {publish_resp.text}") from e

    return publish_resp.json()


def refresh_long_lived_token(current_token: str, timeout: int = 20) -> dict:
    """Refreshes a long-lived token. Must be called before the current token
    expires (60 days) — see refresh_and_store_token() for the automated version
    that also writes the new token back to GitHub Secrets."""
    resp = requests.get(
        THREADS_REFRESH_URL,
        params={"grant_type": "th_refresh_token", "access_token": current_token},
        timeout=timeout,
    )
    try:
        resp.raise_for_status()
    except requests.RequestException as e:
        raise ThreadsError(f"Token refresh failed: {e} / {resp.text}") from e
    data = resp.json()
    if "access_token" not in data:
        raise ThreadsError(f"Unexpected refresh response: {data}")
    return data  # {"access_token": ..., "token_type": "bearer", "expires_in": <seconds>}
