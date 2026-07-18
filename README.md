# US Liquidity Bot — Full Content Rotation + Polls + Threads + LLM Commentary

Automates daily posting to Telegram (and optionally Threads) with a
day-of-week content rotation designed to keep people coming back, plus
event-triggered alerts that fire the moment something noteworthy happens.

```
liquidity_bot/
├── daily_post.py                    # main dispatcher (runs daily via GitHub Actions)
├── refresh_threads_token.py         # keeps the Threads token alive with zero manual work
├── requirements.txt
├── .env.example
├── fonts/                           # Inter (Latin) + NanumGothic bundled
├── lib/
│   ├── fetch_data.py                 # site's own Netlify data source
│   ├── compute_liquidity.py          # net liquidity formula + history builder
│   ├── generate_card.py              # snapshot + weekly recap card images
│   ├── post_telegram.py              # text / photo / native poll
│   ├── post_threads.py               # Threads text/image posting + token refresh
│   ├── github_secrets.py             # self-updates GitHub Secrets (for token refresh)
│   ├── fetch_calendar.py             # FRED official release calendar (Tuesday content)
│   ├── terms.py                      # Friday glossary content
│   ├── knowledge_content.py          # Wednesday liquidity/rate concept rotation
│   ├── signal_scanner.py             # unified any-day urgent scanner (liquidity+rates+combined)
│   ├── triggers.py                   # superseded — folded into signal_scanner.py, kept for reference
│   ├── story.py                      # unused by the current schedule, kept for reference
│   ├── polls.py                      # poll question bank (Sunday engagement)
│   └── llm_content.py                # Gemini/OpenAI commentary, with safe fallback
└── .github/workflows/
    ├── daily_post.yml                 # runs daily_post.py every day
    └── refresh_threads_token.yml      # runs refresh_threads_token.py weekly
```

## Content rotation (redesigned)

Liquidity numbers now post **once a week only** (Monday) — no more repeat
daily snapshots that made back-to-back posts feel like the same content
twice. The Monday card also has **no date/"updated" text** on it by design,
so it doesn't look stale if someone sees it a few days after posting.

| Day | Content | Platforms | Approx. post time (UTC) |
|---|---|---|---|
| Monday | **Weekly Liquidity Result** — speedometer gauge + 1W/4W/13W/26W/52W % change strip + the top-2 drivers behind this week's number | Telegram (photo), Threads (text+image) | 14:00 (~10am ET) |
| Tuesday | **This month's econ calendar** — CPI/NFP/FOMC/GDP/PCE dates for the current calendar month from FRED's official Release Calendar API, past events marked ✅ | Telegram (text), Threads (text) | 14:00 (~10am ET) |
| Wednesday | **Knowledge post** — rotates weekly between a liquidity-indicator concept (TGA / Fed balance sheet / RRP / bank reserves) and a rate concept (Fed Funds / 10Y / 2Y / 10Y-2Y spread / SOFR), each with its own 52-week chart | Telegram (photo), Threads (text+image) | 15:00 (~11am ET) |
| Friday | Term of the Day — rotating finance glossary | Telegram (text+photo), Threads (text+image) | 16:00 (~12pm ET) |
| Sunday | Community engagement — generic opinion poll | Telegram (native poll), Threads (native poll) | 18:00 (~2pm ET) |
| Thu / Sat | No scheduled main post | — | 14:00 (urgent scan only) |
| **Any day** | **Unified urgent scanner** — scans EVERY monitored series (all 4 liquidity components + all 5 rate series + the combined net-flow metric) for the single most notable record / streak / turning-point / big-move signal, and posts it immediately, independent of the schedule above. Posts nothing if nothing is genuinely notable (quality over forced volume). | Telegram + Threads | Checked on every scheduled run |

### Threads link strategy — link goes in the first reply, not the main post

Outbound links in a Threads post's main body are widely reported to get
throttled by Threads' recommendation algorithm. So for every Threads post
(Monday/Tuesday/Wednesday/Friday/urgent scan), `daily_post.py` now:
1. Strips the `SITE_URL` line out of the main post body (leaving a short
   "link in the first reply 👇" hint instead of the actual URL),
2. Publishes that link-free body as the main post,
3. Immediately posts the real link as a **reply** to that same post via
   `lib/post_threads.py` → `reply_to_post()` (uses the `reply_to_id` param).

This only affects Threads — **Telegram captions are unchanged** and still
include the link inline, since Telegram has no such link-suppression
behavior. If the reply post fails for any reason, the main post still goes
up successfully (link-loss is logged, never fatal).

Posting times are chosen within the commonly-cited "best time to post"
window for Western/English-speaking audiences (roughly 9am-1pm ET on
weekdays), spread across Monday/Wednesday/Friday/Sunday so the four
mandatory posts don't cluster together. See `.github/workflows/daily_post.yml`
for the exact cron entries — adjust freely, and note UTC cron times drift by
an hour relative to US Eastern Time across Daylight Saving transitions.

### Rate indicators — confirmed against your actual site data (July 2026)

Checked directly against the `csvfile/` listing in your `fred-data` GitHub
repo. The site does NOT have `DFF` or `T10Y2Y` as raw series — corrected to
the real codes below:

| Bot code | Site label | Site CSV |
|---|---|---|
| `FEDFUNDS` | EFFR 금리 | ✅ `FEDFUNDS.csv` |
| `SOFR` | SOFR 금리 | ✅ `SOFR.csv` |
| `IORB` | IORB 금리 | ✅ `IORB.csv` |
| `DPCREDIT` | 연준 할인율 | ✅ `DPCREDIT.csv` |
| `DGS3MO` | 3개월 미 국채금리 | ✅ `DGS3MO.csv` |
| `DGS2` | 2년물 미 국채금리 | ✅ `DGS2.csv` |
| `DGS10` | 10년물 미 국채금리 | ✅ `DGS10.csv` |
| `RRPONTSYAWARD` | 역레포 금리 | ✅ `RRPONTSYAWARD.csv` |
| *(derived)* `YIELD_SPREAD` = DGS10 − DGS2 | 미국 장단기 금리차 | not a raw CSV on the site either — computed client-side there, mirrored the same way in `lib/signal_scanner.py` / `lib/knowledge_content.py` |
| *(derived)* `SOFR_FEDFUNDS_SPREAD`, `SOFR_IORB_SPREAD` | SOFR 스프레드 지표들 | same — computed from already-fetched raw series, not fetched directly |

All of these feed both the Wednesday knowledge rotation and the any-day
unified urgent scanner.

## Can this really run with zero manual work?

**Telegram: yes, 100%, including polls.** `sendPoll` is a first-class Bot API
endpoint — no special permission needed beyond the bot being a channel admin.

**Threads: yes, for text/image posts AND native polls — one caveat:**
1. **Native polls ARE supported** (Meta added `poll_attachment` support to
   the Threads API in April 2025 — confirmed against Meta's official
   changelog). `lib/post_threads.py` → `publish_poll_post()` posts a real
   Threads poll widget (2-4 options) on Sunday, not a text workaround.
2. **One-time manual OAuth setup is unavoidable** (Meta requires a human to
   click "Allow" once — there's no way around this for any Meta product).
   After that one-time setup, `refresh_threads_token.py` keeps the access
   token alive indefinitely with zero further manual work, because it writes
   the refreshed token back into your GitHub Secrets automatically.

## One-time Threads setup (skip this whole section if you only want Telegram)

1. Make sure your Threads account is linked to an **Instagram Business or
   Creator account**.
2. Go to `https://developers.facebook.com` → Create App → type "Business" →
   add the **Threads** use case.
3. Complete the OAuth consent flow once (Meta's docs walk through this —
   search "Threads API Get Started"): you'll end up with a **short-lived
   token**, which you exchange for a **long-lived token** (valid 60 days)
   and your **THREADS_USER_ID**.
4. Store `THREADS_USER_ID` and `THREADS_ACCESS_TOKEN` as GitHub Secrets.
5. Create a **GitHub Personal Access Token** (classic, `repo` scope, or
   fine-grained with "Secrets: write") so the bot can refresh its own token.
   Store it as the `GH_PAT` secret.
6. Done. `refresh_threads_token.yml` runs weekly and keeps the token alive
   forever without you touching it again.

If you skip Threads setup entirely, everything still works — `daily_post.py`
detects the missing credentials and simply skips the Threads mirror post
(Telegram posting is unaffected).

## LLM commentary setup (Gemini or OpenAI — your choice)

Set `LLM_PROVIDER` to `gemini` (default) or `openai`, and set the matching
API key:

- Gemini: `GEMINI_API_KEY` — free tier available at
  `https://aistudio.google.com/apikey`
- OpenAI: `OPENAI_API_KEY` — `https://platform.openai.com/api-keys`

**If neither is configured, or the API call fails for any reason, the bot
automatically falls back to a deterministic template sentence** — the core
numbers always post; the LLM only adds flavor on top and can never break
the pipeline.

## SITE_URL — confirm this before going live

`SITE_URL` defaults to `https://americayoudongsung.netlify.app/en` in the
code. **Please verify this is your actual live English page URL** and
override it via the `SITE_URL` GitHub Secret if it's different.

## Full environment variable reference

| Variable | Required for | Notes |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Everything | from @BotFather |
| `TELEGRAM_CHAT_ID` | Everything | your channel's chat id |
| `ADMIN_CHAT_ID` | Failure alerts | optional |
| `SITE_API_BASE` | Data fetch | defaults to the Netlify function base |
| `SITE_URL` | Link in captions | **confirm this matches your live EN page** |
| `FRED_API_KEY` | Monday calendar | free, instant: fred.stlouisfed.org/docs/api/api_key.html |
| `THREADS_USER_ID` / `THREADS_ACCESS_TOKEN` | Threads mirror | optional; skipped if unset |
| `GH_PAT` / `GH_REPO` | Threads token self-refresh | `GH_REPO` is auto-filled by `${{ github.repository }}` in the workflow |
| `LLM_PROVIDER` | Angle commentary | `gemini` or `openai`, defaults to `gemini` |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` | Angle commentary | optional; falls back to templates if missing |

## Local testing

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=xxxx
export TELEGRAM_CHAT_ID=xxxx
python daily_post.py
```

The script checks the current UTC day of week and runs the matching branch —
so testing a specific day's content locally means temporarily patching
`datetime.now()` (see the mock tests used during development) or just running
it on that actual day.

## Extending further

- Add more platforms by copying the `lib/post_threads.py` pattern (a
  `publish_text_post()`-shaped function) and calling it from `_mirror_to_threads`-style
  wrapper in `daily_post.py`.
- Add more poll questions to `lib/polls.py` — `GENERIC_LIQUIDITY_POLLS` rotates
  automatically by ISO week number.
- Add more glossary terms to `lib/terms.py` — `TERMS` rotates automatically by
  day-of-year.
- Tune trigger sensitivity in `lib/triggers.py` (`STREAK_ALERT_THRESHOLD`,
  `RECORD_LOOKBACK_WEEKS`).
