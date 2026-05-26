# AI News Tracker — Technical Documentation

A self-hosted aggregator that pulls AI-related signal from research, news,
company blogs, and social platforms; classifies each item by topic and
importance with Claude; and exposes the result through a local web dashboard
that refreshes every 3 hours.

This document covers architecture, data flow, configuration, operations,
troubleshooting, and extension points. For a quickstart, see `README.md`.

---

## 1. Architecture

```
                    ┌─────────────────────────┐
                    │  scheduler.py (every 3h)│
                    └──────────┬──────────────┘
                               │
                ┌──────────────┴───────────────┐
                │                              │
        ┌───────▼────────┐            ┌────────▼────────┐
        │   collectors/   │            │   classifier.py │
        │ rss / arxiv /   │            │  Claude Haiku   │
        │ reddit / hn /   │            │  topic + 1-3    │
        │ bluesky / x     │            │  importance +   │
        └───────┬────────┘            │  why + tldr     │
                │                     └────────┬────────┘
                │                              │
                └──────────────┬───────────────┘
                               │
                       ┌───────▼────────┐
                       │  storage/db.py │
                       │   SQLite       │
                       └───────┬────────┘
                               │
                       ┌───────▼────────┐
                       │   web/app.py   │
                       │  FastAPI + Jinja│
                       │   port 8765     │
                       └────────────────┘
```

### Components

| Component        | Purpose                                                  | Tech              |
|------------------|----------------------------------------------------------|-------------------|
| `collectors/`    | One module per source; produces normalized item dicts    | `feedparser`, `httpx`, `arxiv` |
| `classifier.py`  | Provider-agnostic LLM batches (Anthropic or OpenAI)      | Anthropic / OpenAI SDK |
| `storage/db.py`  | Persistence + queries                                    | SQLite (stdlib)   |
| `scheduler.py`   | Orchestrator: collect, dedupe, insert, classify          | sync Python       |
| `web/app.py`     | Dashboard rendering                                      | FastAPI + Jinja2  |
| `scripts/`       | Install, launchd plist, RSSHub setup                     | bash, plist       |

### Process model

The system has two processes:

1. **Scheduler** — short-lived, fired every 3 hours by `launchd`. Runs
   `scheduler.py`, which collects, classifies, writes, and exits.
2. **Web** — long-lived, started manually with `bash scripts/run_web.sh`.
   Reads from the same SQLite file but never writes to it.

Both processes share the database via SQLite's file-locking. The web process
holds only short-lived read connections, so the scheduler's writes never
block it.

---

## 2. Data flow

### 2.1 Collection

Each collector returns a list of dicts with this shape:

```python
{
  "source":       "OpenAI",            # display label
  "source_type":  "rss",               # rss | arxiv | reddit | bluesky | x | hn
  "url":          "https://...",       # canonical URL — used as dedupe key
  "title":        "...",
  "summary":      "...",               # cleaned, truncated to 600 chars
  "author":       "...",
  "published_at": "2026-04-20T09:00Z", # ISO 8601 UTC
  "topic":        "Frontier Models",   # hint from feed config; classifier may overwrite
}
```

The orchestrator concatenates results from all collectors, dedupes by URL
in memory, then attempts inserts. SQLite's `UNIQUE(url)` constraint
guarantees a stable second-line dedupe across runs.

### 2.2 Classification

After insert, the orchestrator selects all rows where `importance IS NULL`
(items never seen by the classifier — newly inserted, plus any that failed
prior classification). It batches them 10 at a time, asks Claude for a
JSON array of `{topic, importance, why, tldr}`, and writes the result
back via `update_classification`.

The classifier prompt enforces:
- `topic` ∈ allowed list from `config.yaml`
- `importance` ∈ {1, 2, 3}, with a rubric biased against routine items
- `why` ≤ 15 words
- `tldr` ≤ 25 words, written for a busy executive

If the API call fails after 3 retries, items are written with `importance=1`
and `why="classifier error"` so they still appear (downgraded) and can be
re-tried on the next run.

### 2.3 Storage

```sql
items(
  id, source, source_type, url UNIQUE,
  title, summary, author,
  published_at, collected_at,
  topic, importance, importance_why, tldr,
  raw_json
)
runs(
  id, started_at, finished_at,
  items_found, items_new, errors
)
```

Indexes cover the dashboard's query patterns: `published_at DESC`, `topic`,
`importance DESC`, `collected_at DESC`. SQLite's `datetime()` does the
time-window filtering directly.

### 2.4 Rendering

`web/app.py` exposes a single route `/` that:

1. reads items in window with optional topic filter
2. groups them by importance into 4 buckets (3, 2, 1, None)
3. computes per-topic counts (used in tab badges)
4. computes 14-day daily volume (sparkline)
5. computes today's count (top-left counter)

The template renders an importance-grouped, latest-first list per topic
tab. No JavaScript — pure server-side render with `?topic=&hours=` query
params.

---

## 3. Configuration

All knobs live in `config.yaml`:

```yaml
provider: anthropic    # anthropic | openai
models:
  anthropic: claude-haiku-4-5-20251001
  openai:    gpt-5-mini

lookback_hours: 24
max_items_per_source: 30

topics: [...]         # exact labels the classifier must use
rss_feeds: [...]      # company blogs, news sites, HN-as-RSS
arxiv_categories: [...]
reddit_subs: [...]
bluesky_handles: [...]
rsshub_url: ""        # empty = X collector skipped
x_handles: [...]
high_signal_keywords: [...]
```

### Switching providers

Edit `provider:` in `config.yaml`, drop the matching key in `.env`, restart
the scheduler. The prompt and output format are identical across both
providers — same `topic / importance / why / tldr` schema. Adding a new
provider (e.g. Gemini, Ollama) is a ~30-line subclass of `BaseClassifier`
in `classifier.py`.

### Adding a new RSS feed

```yaml
rss_feeds:
  - name: "Cohere Blog"
    url: "https://cohere.com/blog/rss.xml"
    topic: "Frontier Models"
```

The `topic` key is a hint stored on insert; the classifier may overwrite it
based on the actual content. To bypass classification (always trust the
hint), modify `classifier.py` to read existing `topic` and skip the call.

### Adding a Bluesky handle

Resolve the handle first to confirm it exists:

```bash
curl "https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle?handle=NEW_HANDLE"
```

If it returns a `did`, add it to `bluesky_handles`. If it returns 400, the
handle is wrong — try the user's profile URL from bsky.app.

### Adding an X handle

Requires the optional RSSHub setup (`scripts/setup_rsshub.md`). Once
RSSHub is running, just add the handle (no `@`) to `x_handles`.

### Tuning importance

Importance is set entirely by the classifier prompt in `classifier.py`
(`SYSTEM_PROMPT`). To shift the distribution, edit the rubric. Examples:

- More aggressive level-3: add "any benchmark improvement >5pp counts as 3"
- Less Social Buzz noise: add "Bluesky/Reddit posts default to 1 unless cited"

You can re-classify the entire database without re-collecting:

```bash
sqlite3 data/news.db "UPDATE items SET importance=NULL, topic=NULL;"
python scheduler.py
```

The scheduler will skip collection (everything dedupes), and the classifier
will run on every row.

---

## 4. Operations

### 4.1 First-time setup

```bash
cd ai-news-tracker
bash scripts/install.sh                 # venv + deps + DB init
python scheduler.py                     # first collection
bash scripts/run_web.sh                 # start web on :8765
bash scripts/install_launchd.sh         # enable 3h auto-refresh
```

### 4.2 Daily operations

| Action                                  | Command                                                  |
|-----------------------------------------|----------------------------------------------------------|
| Manually trigger a collection           | `python scheduler.py`                                    |
| Restart the web server                  | `bash scripts/run_web.sh`                                |
| Tail collection logs                    | `tail -f logs/scheduler.log`                             |
| Tail launchd output                     | `tail -f logs/launchd.{out,err}.log`                     |
| Check launchd status                    | `launchctl list \| grep ainews`                          |
| Pause auto-refresh                      | `launchctl unload ~/Library/LaunchAgents/com.ainews.tracker.plist` |
| Resume auto-refresh                     | `launchctl load ~/Library/LaunchAgents/com.ainews.tracker.plist`   |
| Re-classify everything                  | `sqlite3 data/news.db "UPDATE items SET importance=NULL;"` then `python scheduler.py` |
| Reset the DB completely                 | `rm data/news.db; python -c "from storage import db; db.init_db()"` |

### 4.3 Cost & rate limits

- **Anthropic**: ~$0.05–0.15 per run with Haiku 4.5 at typical volumes
  (200–300 new items/run, 10 per batch). At 8 runs/day (every 3h), most
  runs find <50 new items so cost scales sub-linearly — expect $10–25/month.
  The classifier uses `tenacity` to retry on 429 with exponential backoff.
- **arXiv**: built-in 3-second delay between requests (handled by `arxiv` lib).
- **Reddit**: requires `User-Agent`. Free tier is generous for ~5 subs.
- **Bluesky**: public, no rate limits encountered in practice.
- **HN Algolia**: no auth, no documented limit.
- **X / RSSHub**: depends on the auth_token cookie; expect to refresh
  every few weeks.

### 4.4 Logs

| File                          | Source                          |
|-------------------------------|---------------------------------|
| `logs/scheduler.log`          | Python logging from `scheduler.py` |
| `logs/launchd.out.log`        | stdout of `python scheduler.py` when launched by launchd |
| `logs/launchd.err.log`        | stderr (Python tracebacks land here) |

---

## 5. Web UI reference

### Route

`GET /?topic=<TopicName>&hours=<24|48|72|168>`

- `topic` defaults to `All`; matches the `topic` column exactly. Special
  value `All` skips the filter.
- `hours` defaults to `168` (1 week). Any positive integer works; the
  buttons in the UI happen to use 24/48/72/168.

### Sections

1. **Header**: site title + last-run timestamp + new/found counts.
2. **Stat cards**: today's count, major / notable / routine in the current
   window, plus a 14-day daily-volume sparkline.
3. **Tabs**: one per topic; badge shows count in the current window.
4. **Window selector**: 24h / 48h / 72h / 168h.
5. **Buckets**: Major (level 3), Notable (level 2), Routine (level 1),
   Unclassified (None). Each item shows title (linked), source, type,
   topic, published time, tldr, and the classifier's "why".

### `/health`

Returns `{ok, last_run}` for liveness checks.

---

## 6. Extending the system

### Adding a new collector

1. Create `collectors/<name>.py` exporting `collect(...) -> list[dict]`.
2. Each item must include all fields listed in §2.1.
3. Wire it into `scheduler.collect_all`:
   ```python
   log.info("Collecting <name>...")
   all_items.extend(<name>.collect(cfg["<name>_config"]))
   ```
4. Add config to `config.yaml`.

### Adding a new topic

1. Add the label to `topics` in `config.yaml`.
2. Restart the web server (template re-reads on each request).
3. Re-classify if you want existing items to use it:
   `sqlite3 data/news.db "UPDATE items SET importance=NULL;"`.

### Email/Slack digest

The cleanest add: a small `digest.py` that reads `db.fetch_items(hours=12,
importance>=2)`, formats a Markdown summary, and posts it. Hook it after
classification in `scheduler.run`:

```python
if items_new:
    digest.send(db.fetch_items(since_hours=12))
```

Slack: `requests.post(SLACK_WEBHOOK_URL, json={"text": markdown})`.

### Per-source weighting

If you want a source to count more (e.g. Anthropic blog always 3+), add
the source to `high_signal_keywords` or pre-set importance in the
collector before insert:

```python
if it["source"] in ("OpenAI", "Anthropic"):
    it["importance"] = 3
```

The classifier will then skip it because `WHERE importance IS NULL`
filters it out.

---

## 7. Troubleshooting

### `ANTHROPIC_API_KEY not set` even though `.env` exists

`python-dotenv` does not override existing environment variables by
default. If something earlier in the shell set the var to an empty string,
`load_dotenv` quietly leaves it. The fix in `scheduler.py` is:

```python
load_dotenv(ROOT / ".env", override=True)
```

### "No items in this window" after a fresh install

The default window is 168h. If your DB is empty, run `python scheduler.py`
once. If items are old (the system clock thinks "now" is later than your
items' `published_at`), re-run the scheduler — the latest run date will
update.

### Reddit returns "not well-formed (invalid token)"

Reddit's `.rss` endpoint returns HTML when the user-agent looks like a
bot. The current Reddit collector uses the JSON endpoint instead. If you
revert to RSS, set:

```python
feedparser.parse(url, agent="ai-news-tracker/1.0 by your-handle")
```

### Bluesky returns 400 on resolveHandle

The handle doesn't exist or moved. Check at
`https://bsky.app/profile/<handle>` — if it 404s, drop or replace it in
`config.yaml`.

### X collector finds nothing

If `rsshub_url` is set but RSSHub returns empty feeds, the auth_token has
likely expired. From `scripts/setup_rsshub.md`:

```bash
docker rm -f rsshub
docker run -d --name rsshub --restart=always -p 1200:1200 \
  -e TWITTER_AUTH_TOKEN=<fresh_token> diygod/rsshub
```

### launchd job not running

```bash
launchctl list | grep ainews                  # exit code should be present
launchctl unload ~/Library/LaunchAgents/com.ainews.tracker.plist
launchctl load   ~/Library/LaunchAgents/com.ainews.tracker.plist
tail -f logs/launchd.err.log                  # check for ImportError or path issues
```

The plist hard-codes the venv path. If you moved the project, regenerate
the plist from `scripts/com.ainews.tracker.plist` with the correct path,
then re-`load`.

### Classifier returns inconsistent topics

Models occasionally invent variants ("Frontier model" vs "Frontier
Models"). The orchestrator keeps whatever Claude returns. To enforce
strict matching, post-process in `update_classification`:

```python
if topic not in ALLOWED_TOPICS:
    topic = "Applications"
```

### Costs spiking

Two common causes:
1. Many feeds returning many items per run. Lower `max_items_per_source`.
2. Repeated classification of the same items because something cleared
   `importance`. Check `runs.errors` for a pattern.

---

## 8. File reference

```
ai-news-tracker/
├── .env                     # ANTHROPIC_API_KEY (chmod 600, gitignored)
├── .gitignore
├── README.md                # quickstart
├── doc.md                   # this file
├── requirements.txt
├── config.yaml              # all tunables
├── scheduler.py             # entry point for every-3h run
├── classifier.py            # Claude batch classifier
├── collectors/
│   ├── __init__.py
│   ├── rss.py               # generic RSS/Atom
│   ├── arxiv_c.py           # arXiv via arxiv lib
│   ├── reddit_c.py          # JSON endpoint with UA
│   ├── bluesky.py           # public AT proto
│   ├── hn.py                # HN Algolia search
│   └── x_twitter.py         # RSSHub-backed
├── storage/
│   └── db.py                # SQLite + queries
├── web/
│   ├── app.py               # FastAPI app (single route)
│   ├── templates/
│   │   └── index.html       # Jinja2
│   └── static/
│       └── style.css
├── scripts/
│   ├── install.sh           # venv + deps + db init
│   ├── install_launchd.sh   # registers the plist
│   ├── run_web.sh           # uvicorn launcher
│   ├── com.ainews.tracker.plist
│   └── setup_rsshub.md      # X collector setup
├── data/
│   └── news.db              # SQLite (created on first run)
└── logs/
    ├── scheduler.log
    ├── launchd.out.log
    └── launchd.err.log
```

---

## 9. Security notes

- `.env` is `chmod 600` and listed in `.gitignore`. The API key never
  leaves the machine.
- The web server binds to `127.0.0.1` only — not reachable from other
  devices on the network.
- No authentication is implemented; assumes the only user is whoever has
  shell access to the machine.
- The X collector path requires a throwaway X account's `auth_token`
  cookie; using your main account risks suspension and is strongly
  discouraged.
- LinkedIn is intentionally not supported — every legal free path was
  evaluated and rejected as either dead, fragile, or violating CFAA-tested
  precedent (`hiQ v. LinkedIn`).

---

## 10. Known limitations

- **Single-machine.** No horizontal scaling, no shared DB. SQLite is fine
  for ~100k items but not 10M.
- **No deduplication across sources.** The same story published on TechCrunch
  and The Verge yields two items with different URLs.
- **No translation.** Non-English content (e.g. Bluesky posts in Swedish)
  passes straight through to the classifier; Claude usually handles it but
  topic assignment is less accurate.
- **No image/video.** Sources are treated as text-only.
- **Backfill is manual.** If the launchd job misses a run (laptop closed),
  a 12-hour window is lost. The next run still picks up everything in the
  current `lookback_hours` window, so loss is bounded.
