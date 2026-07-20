# US Liquidity Bot — Full Content Rotation + Polls + Threads + LLM Commentary

Automates daily posting to Telegram (and optionally Threads) with a
day-of-week content rotation, LLM-written "why it matters" context on every
data post, and event-triggered alerts that fire the moment something
noteworthy happens — anywhere across liquidity, rates, or the combined
metric, not just the scheduled topic of the day.

```
liquidity_bot/
├── daily_post.py                    # main dispatcher (runs daily via GitHub Actions)
├── daily_news.py                    # SEPARATE daily news pick — own schedule, no links, see below
├── refresh_threads_token.py         # keeps the Threads token alive with zero manual work
├── requirements.txt
├── .env.example
├── fonts/                           # Inter (Latin) + NanumGothic bundled
├── lib/
│   ├── fetch_data.py                 # site's own Netlify data source
│   ├── compute_liquidity.py          # net liquidity formula + percentile Liquidity Index
│   ├── generate_card.py              # ALL card images — one shared "Candidate C" visual style
│   ├── post_telegram.py              # text / photo / native poll
│   ├── post_threads.py               # Threads text/image/poll/reply posting + token refresh
│   ├── github_image_host.py          # commits card images to the repo for a public Threads URL
│   ├── github_secrets.py             # self-updates GitHub Secrets (for token refresh)
│   ├── fetch_calendar.py             # FRED official release calendar + top-3 ranking (Tuesday)
│   ├── terms.py                      # Friday glossary content (with monogram badges)
│   ├── knowledge_content.py          # Wednesday/Thursday liquidity/rate concept rotation
│   ├── signal_scanner.py             # unified any-day urgent scanner (liquidity+rates+combined)
│   ├── signal_state.py               # 14-day dedup for the urgent scanner (NEW)
│   ├── news_sources.py               # RSS source list + relevance keywords (NEW)
│   ├── news_fetcher.py               # fetches/parses/prefilters RSS candidates (NEW)
│   ├── news_state.py                 # 45-day dedup for the daily news pick (NEW)
│   ├── news_scanner.py               # orchestrates fetch -> dedup -> LLM pick (NEW)
│   ├── llm_content.py                # Gemini/OpenAI commentary, with safe fallback everywhere
│   ├── reply_templates.py            # private admin-only "reply guy" snippet generator
│   ├── triggers.py                   # superseded — folded into signal_scanner.py, kept for reference
│   ├── story.py                      # unused by the current schedule, kept for reference
│   └── polls.py                      # poll question bank (Sunday engagement)
└── .github/workflows/
    ├── daily_post.yml                 # runs daily_post.py on its weekday schedule
    ├── daily_news.yml                 # runs daily_news.py once a day, own schedule (NEW)
    └── refresh_threads_token.yml      # runs refresh_threads_token.py weekly
```

## Daily News Pick (separate from the 7-day rotation)

`daily_news.py` runs **once a day, every day, at a fixed time (13:35 UTC —
just after the US market open)**, completely independent of `daily_post.py`'s
weekday schedule. It scans RSS feeds from the Fed, Treasury, and major
financial media (see `lib/news_sources.py`) for the single story most likely
to move US dollar liquidity conditions, and posts a short paraphrased summary
+ a plain "expected impact" line.

**Design specifics (per explicit spec):**
- **No links at all** — neither to the original article nor to the dashboard
  site. Attribution is by **source name only** (e.g. "Source: Federal
  Reserve"), shown on the card and in the caption footer.
- **Silence is correct** — if nothing genuinely relevant is found, or
  everything found was already covered recently, it posts nothing. It never
  forces a filler post just to hit a daily quota.
- **45-day dedup** — `lib/news_state.py` remembers which stories were already
  posted (by article link) so the same story never repeats, even across
  separate GitHub Actions runs (state is committed back into the repo, same
  trick as the image-hosting module).
- **Requires an LLM key** (Gemini or OpenAI) — this feature has no
  template-only fallback for the pick/summary itself (picking "the most
  relevant story" isn't something a fixed template can do). Without a key
  configured, it will correctly find nothing to post every day rather than
  guessing.
- **Kept separate from the urgent data-signal scanner on purpose** — tying a
  qualitative news story to a specific quantitative data spike reliably would
  require the LLM to correctly infer cause-and-effect across two very
  different data types, which is a much harder and more error-prone problem.
  Two independent, simpler scanners is the more robust design.

## Urgent Signal Scanner — now with 14-day dedup

Previously the urgent scanner (`lib/signal_scanner.py`) could re-post the
exact same signal every single day, because the underlying weekly-cadence
series (TGA, WALCL, RRP, etc.) only actually change once a week — so the same
"TGA falling for 29 straight weeks" fact would still be true, and get posted
again, the next day. Fixed via `lib/signal_state.py`: after a signal is
posted, its `(ticker, signal_type)` pair is remembered for **14 days**, and
if the single top-ranked signal is still the same story, the scanner posts
**nothing** that day rather than repeating it or falling back to a weaker
second-best signal.

## Content rotation


Liquidity numbers post **once a week only** (Monday) — no repeat daily
snapshots that make back-to-back posts feel like the same content twice.
The Monday gauge card also has **no date/"updated" text** on it by design,
so it doesn't look stale if someone sees it a few days after posting.

Every scheduled post now **always carries an image**, uses **no hashtags**,
and includes a short **LLM-written "why it matters" line** explaining why
that specific data point is worth paying attention to right now (calm,
informational tone — not hype; falls back to a template sentence if the LLM
call fails, so a post never goes out with a broken commentary section).

| Day | Content | Images | Platforms | Approx. post time (UTC) |
|---|---|---|---|---|
| Monday | **Weekly Liquidity Index** — the site's own percentile-rank gauge (dome-up speedometer, 0=UNDERSUPPLY, 100=FLOODED) + top-2 drivers, **plus** a 52-week NETMARKETFLOW trend chart | 2 images (gauge + trend chart) | Telegram (2 photos), Threads (image post + trend chart as a 2nd reply in the same thread) | 14:00 (~10am ET) |
| Tuesday | This month's econ calendar — full list as a calendar image, caption highlights the **top-3 most important upcoming releases** + an LLM explanation of why the #1 release matters | 1 (calendar) | Telegram (photo), Threads (image) | 14:00 (~10am ET) |
| Wednesday **and** Thursday | **Identical routine** — a knowledge post rotating weekly between a liquidity-indicator concept and a rate concept, each with its own 52-week chart card + LLM "why it matters" line + a closing open-ended question | 1 (chart) | Telegram (photo), Threads (image) | 15:00 (~11am ET), same time both days |
| Friday | Term of the Day — illustrated card (monogram badge, e.g. "TGA") + LLM "why it matters" line | 1 (illustrated card) | Telegram (photo), Threads (image) | 16:00 (~12pm ET) |
| Sunday | Community engagement — generic opinion poll | — (native poll, no image) | Telegram (native poll), Threads (native poll) | 18:00 (~2pm ET) |
| Saturday | No scheduled main post | — | — | 14:00 (urgent scan only) |
| **Any day** | **Unified urgent scanner** — scans EVERY monitored series (4 liquidity components + 8 rate series + 3 derived spreads + the combined net-flow metric) for the single most notable record/streak/turning-point/big-move signal, with its own chart + LLM "why it matters" line, posted immediately and independent of the schedule above. Posts nothing if nothing is genuinely notable (quality over forced volume). | 1 (chart) | Telegram + Threads | Checked on every scheduled run |

Why Wednesday and Thursday are identical: this was a deliberate request —
same function (`run_knowledge_content()`), same chart style, same posting
time on both days, just running twice in the week so the knowledge series
gets more airtime without duplicating the Monday/Tuesday content.

### Card design — "Candidate C" (chosen from 4 design candidates)

All card images (`lib/generate_card.py`) share one visual language: a white
rounded card on a light page background, blue accent color, pill-shaped
badges, and gradient-fill line charts. Four functions cover every card type:

- `create_gauge_card()` — Monday's Liquidity Index gauge
- `create_metric_chart_card()` — Wednesday/Thursday knowledge charts,
  Monday's NETMARKETFLOW trend chart, and the urgent scanner's chart
- `create_calendar_card()` — Tuesday's monthly calendar
- `create_term_icon_card()` — Friday's illustrated glossary card

### The Liquidity Index — matches the site exactly, not a made-up formula

Checked directly against `index.html`'s `renderLiquidityIndexGauge()`: the
number is a **percentile rank** of this week's NETMARKETFLOW value against
its own historical distribution (0 = most drained week ever seen,
100 = most flooded), NOT a linear rescaling of the dollar value. The gauge
geometry (dome-up semicircle, pivot at the bottom, blue→yellow→red
gradient, "UNDERSUPPLY"/"FLOODED" edge labels) and the status thresholds
(≥70 Liquidity Expansion, ≤30 Liquidity Contraction, else Neutral) are
copied from the site's own logic — see `compute_liquidity_index()` in
`lib/compute_liquidity.py`. The 1W/4W/12W/52W change strip is in
**percentile points (%p)**, matching the site's own stat row exactly.

### Threads link strategy — link goes in the first reply, not the main post

Outbound links in a Threads post's main body are widely reported to get
throttled by Threads' recommendation algorithm. So for every Threads post,
`daily_post.py`:
1. Strips the `SITE_URL` line out of the main post body (leaving a short
   "link in the first reply 👇" hint instead of the actual URL),
2. Publishes that link-free body as the main post,
3. Immediately posts the real link as a **reply** via
   `lib/post_threads.py` → `reply_to_post()` (`reply_to_id` param).

Monday additionally posts its NETMARKETFLOW trend chart as a **second
reply** in the same thread (`reply_to_post(..., image_url=...)`), so the
main feed shows one post for the slot while the thread carries both images.

This only affects Threads — **Telegram captions are unchanged** and still
include the link inline. If a reply fails for any reason, the main post
still goes up successfully (logged, never fatal).

### Reach-strategy checklist — what's applied and why

Everything marked "recommended" in our earlier discussion is now automated;
the only unchecked item is intentionally manual (see below).

| Method | Status | What was actually changed |
|---|---|---|
| Remove hashtags | ✅ Applied | Every caption builder (`llm_content.py`, `terms.py`, `fetch_calendar.py`, the Monday/Wednesday/urgent captions in `daily_post.py`) now ends at the link line — no `#tags` anywhere, either platform. |
| Always attach a chart/image | ✅ Applied | Tuesday and Friday were text-only before — both now post a real image (`create_calendar_card`, `create_term_icon_card`). Also fixed the underlying bug that caused Threads image posts to silently fall back to text (see below). |
| Link in first reply | ✅ Already applied, extended | Now also covers Tuesday/Wednesday/Thursday/Friday (previously only Monday/urgent), plus Monday's second image goes in a reply too. |
| Closing open-ended question | 🟡 Applied selectively | Added to Wednesday/Thursday knowledge posts only (Sunday's poll already *is* the engagement hook) — not on every post, so it doesn't feel forced. |
| Posting-frequency consistency | ✅ Already satisfied | The fixed weekly schedule itself covers this; no code change needed. |
| Reply-guy strategy | ✅ Infra kept, still manual | `lib/reply_templates.py` + `_send_daily_reply_toolkit()` still generates ready-to-paste reply snippets sent privately to `ADMIN_CHAT_ID` each run — actually posting them on other accounts' threads is a human action by design (an API can't do this safely/appropriately on your behalf). |
| Seeding initial engagement | ⬜ Not automated | Left as a manual practice note, not code — asking real people to like/comment works, but automating fake engagement risks account penalties and wasn't something to build. |
| @-mention spam | ⬜ N/A | Never used anywhere in this codebase to begin with. |

### Threads image-posting bug — fixed

The earlier missing-image issue (Threads post going out as text-only even
though a chart was generated) was `lib/github_image_host.py` returning the
`raw.githubusercontent.com` URL immediately after `git push`, before
GitHub's CDN had actually finished serving the file — Threads would then
fail to fetch it server-side and the code silently fell back to text.
Fixed: `publish_image_to_repo()` now polls the URL with `HEAD` requests
(up to 6 attempts, 2s apart) and only returns once it's confirmed live.

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

## Can this really run with zero manual work?

**Telegram: yes, 100%, including polls.** `sendPoll` is a first-class Bot API
endpoint — no special permission needed beyond the bot being a channel admin.

**Threads: yes, for text/image posts, polls, AND replies — one caveat:**
1. **Native polls ARE supported** (Meta added `poll_attachment` support to
   the Threads API in April 2025). `publish_poll_post()` posts a real
   Threads poll widget (2-4 options) on Sunday.
2. **One-time manual OAuth setup is unavoidable** (Meta requires a human to
   click "Allow" once). After that, `refresh_threads_token.py` keeps the
   access token alive indefinitely with zero further manual work.

## One-time Threads setup (skip this whole section if you only want Telegram)

1. Make sure your Threads account is linked to an **Instagram Business or
   Creator account**.
2. Go to `https://developers.facebook.com` → Create App → type "Business" →
   add the **Threads** use case.
3. Complete the OAuth consent flow once: you'll end up with a **short-lived
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

Used for: the Tue/Wed/Thu/Fri/urgent "why it matters" lines
(`generate_why_it_matters`, `generate_calendar_commentary` in
`lib/llm_content.py`), plus the existing angle/fact-caption/open-question
helpers. **If neither key is configured, or a call fails for any reason,
every one of these falls back to a deterministic template sentence** — the
core numbers and facts always post; the LLM only adds explanatory flavor on
top and can never break the pipeline.

## SITE_URL — confirm this before going live

`SITE_URL` defaults to `https://americayoudongsung.netlify.app/en` in the
code. **Please verify this is your actual live English page URL** and
override it via the `SITE_URL` GitHub Secret if it's different.

## Full environment variable reference

| Variable | Required for | Notes |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Everything | from @BotFather |
| `TELEGRAM_CHAT_ID` | Everything | your channel's chat id |
| `ADMIN_CHAT_ID` | Failure alerts + reply toolkit | optional |
| `SITE_API_BASE` | Data fetch | defaults to the Netlify function base |
| `SITE_URL` | Link in captions | **confirm this matches your live EN page** |
| `FRED_API_KEY` | Tuesday calendar | free, instant: fred.stlouisfed.org/docs/api/api_key.html |
| `THREADS_USER_ID` / `THREADS_ACCESS_TOKEN` | Threads mirror | optional; skipped if unset |
| `GH_PAT` / `GH_REPO` | Threads token self-refresh + image hosting | `GH_REPO` is auto-filled by `${{ github.repository }}` in the workflow |
| `LLM_PROVIDER` | "Why it matters" commentary | `gemini` or `openai`, defaults to `gemini` |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` | "Why it matters" commentary | optional; falls back to templates if missing |

## Local testing

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=xxxx
export TELEGRAM_CHAT_ID=xxxx
python daily_post.py
```

The script checks the current UTC day of week and runs the matching branch —
so testing a specific day's content locally means temporarily patching
`datetime.now()` or just running it on that actual day.

## Extending further

- Add more platforms by copying the `lib/post_threads.py` pattern.
- Add more poll questions to `lib/polls.py` — `GENERIC_LIQUIDITY_POLLS` rotates
  automatically by ISO week number.
- Add more glossary terms to `lib/terms.py` — `TERMS` rotates automatically by
  day-of-year; give each one a short `"badge"` monogram.
- Add more knowledge topics to `lib/knowledge_content.py`'s `LIQUIDITY_TOPICS`
  / `RATE_TOPICS` lists.
- Tune `RELEASE_PRIORITY` in `lib/fetch_calendar.py` to change which release
  Tuesday considers "most important."
