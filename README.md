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
│   ├── fetch_calendar.py             # FRED official release calendar
│   ├── terms.py                      # Saturday glossary content
│   ├── story.py                      # Sunday record/streak narrative
│   ├── triggers.py                   # streak / record / turning-point alerts (any day)
│   ├── polls.py                      # poll question bank (calendar-matched + generic)
│   └── llm_content.py                # Gemini/OpenAI commentary, with safe fallback
└── .github/workflows/
    ├── daily_post.yml                 # runs daily_post.py every day
    └── refresh_threads_token.yml      # runs refresh_threads_token.py weekly
```

## Content rotation

| Day | Content | Platforms |
|---|---|---|
| Monday | This week's major US econ releases (CPI/NFP/FOMC/GDP/PCE) via FRED's official calendar API, plus a poll matched to whichever event is on the calendar | Telegram (text+poll), Threads (text+open question) |
| Tue-Thu | Daily snapshot card, with an LLM-generated "angle" line (comparison / record / cause / question / warning — picked at random) so the same number never reads the same way twice | Telegram (photo), Threads (text) |
| Friday | Weekly recap bar chart (last 8 weeks) | Telegram (photo), Threads (text) |
| Saturday | Term of the Day — rotating finance glossary, no data fetch needed | Telegram (text), Threads (text) |
| Sunday | "This week by the numbers" record/streak story + a generic opinion poll | Telegram (text+poll), Threads (text+LLM open question) |
| **Any day** | Streak alert (4+ consecutive weeks same direction), record alert (26-week high/low), and turning-point alert (direction flip) — checked on every run and posted immediately if triggered | Telegram + Threads |

## Can this really run with zero manual work?

**Telegram: yes, 100%, including polls.** `sendPoll` is a first-class Bot API
endpoint — no special permission needed beyond the bot being a channel admin.

**Threads: yes, for text/image posts — but two caveats:**
1. **Polls are not supported by the Threads API at all** (as of 2026, it's
   text/image/video/carousel only). That's why Threads gets an "open question"
   version instead of a real poll widget.
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
