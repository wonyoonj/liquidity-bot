# -*- coding: utf-8 -*-
"""
Updates a GitHub Actions repository secret programmatically, so the Threads
access token can refresh itself with zero human intervention.

Requires:
    - GH_PAT: a GitHub Personal Access Token with "repo" scope (classic) or
      "Secrets: write" (fine-grained), stored as a GitHub Secret itself.
    - GH_REPO: "owner/repo", e.g. "yourname/liquidity-bot"
    - PyNaCl (see requirements.txt) — GitHub requires secrets to be encrypted
      client-side with libsodium's sealed-box scheme before upload.

This is the same mechanism GitHub's own docs recommend for "secret rotation"
workflows: https://docs.github.com/en/rest/actions/secrets
"""
from __future__ import annotations

import os
import base64
import requests
from nacl import encoding, public


class GitHubSecretError(RuntimeError):
    pass


def _get_config():
    pat = os.environ.get("GH_PAT")
    repo = os.environ.get("GH_REPO")
    if not pat or not repo:
        raise GitHubSecretError("GH_PAT / GH_REPO is not set — cannot self-update secrets.")
    return pat, repo


def _encrypt_secret(public_key_b64: str, secret_value: str) -> str:
    public_key = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def update_repo_secret(secret_name: str, secret_value: str, timeout: int = 20) -> None:
    pat, repo = _get_config()
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    key_resp = requests.get(
        f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
        headers=headers, timeout=timeout,
    )
    try:
        key_resp.raise_for_status()
    except requests.RequestException as e:
        raise GitHubSecretError(f"Failed to fetch repo public key: {e} / {key_resp.text}") from e

    key_data = key_resp.json()
    encrypted_value = _encrypt_secret(key_data["key"], secret_value)

    put_resp = requests.put(
        f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}",
        headers=headers,
        json={"encrypted_value": encrypted_value, "key_id": key_data["key_id"]},
        timeout=timeout,
    )
    try:
        put_resp.raise_for_status()
    except requests.RequestException as e:
        raise GitHubSecretError(f"Failed to update secret '{secret_name}': {e} / {put_resp.text}") from e
