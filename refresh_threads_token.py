# -*- coding: utf-8 -*-
"""
ONE-TIME helper script — run this manually on your own computer, just once,
to convert the token you got from Meta's "User Token Generator" into a
60-day long-lived token, and to look up your THREADS_USER_ID.

Usage:
    pip install requests
    python get_threads_token.py

It will ask you to paste 3 things (App Secret, the token from step 4, and
your Threads username) and then print exactly what to paste into your
GitHub Secrets: THREADS_USER_ID and THREADS_ACCESS_TOKEN.
"""
import requests

print("=== Threads long-lived token helper ===\n")
app_secret = input("Paste your App Secret (from App settings -> Basic): ").strip()
short_token = input("Paste the token from the 'User Token Generator' step: ").strip()

print("\n[1/2] Exchanging for a 60-day long-lived token...")
resp = requests.get(
    "https://graph.threads.net/access_token",
    params={
        "grant_type": "th_exchange_token",
        "client_secret": app_secret,
        "access_token": short_token,
    },
)

if resp.status_code != 200:
    print(f"\n[FAILED] {resp.status_code}: {resp.text}")
    print(
        "\nIf the error mentions the token is already long-lived, that's fine —\n"
        "just use the token from step 4 directly as your THREADS_ACCESS_TOKEN."
    )
    raise SystemExit(1)

data = resp.json()
long_lived_token = data["access_token"]
expires_days = round(data.get("expires_in", 0) / 86400, 1)
print(f"  -> Success! Valid for about {expires_days} days.")

print("\n[2/2] Looking up your THREADS_USER_ID...")
me_resp = requests.get(
    "https://graph.threads.net/v1.0/me",
    params={"fields": "id,username", "access_token": long_lived_token},
)
me_resp.raise_for_status()
me_data = me_resp.json()

print("\n" + "=" * 60)
print("COPY THESE INTO YOUR GITHUB SECRETS:")
print("=" * 60)
print(f"THREADS_USER_ID       = {me_data['id']}")
print(f"THREADS_ACCESS_TOKEN  = {long_lived_token}")
print("=" * 60)
print(f"\n(Confirmed account: @{me_data.get('username', '?')})")
print("\nThis long-lived token is valid ~60 days. After you set up")
print("refresh_threads_token.py + the weekly GitHub Action, it will")
print("keep refreshing itself automatically — you won't need to run")
print("this script again unless something breaks.")
