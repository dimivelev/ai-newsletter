# AI News Tracker

Local daily AI news aggregator. Pulls from research papers, company blogs,
news sites, social (Bluesky + optional X), Reddit, Hacker News. Claude
classifies each item by topic and importance. Runs every 3h via launchd.
Web UI on `http://127.0.0.1:8765`.

## Sources

| Source              | Access        | Setup required            |
|---------------------|---------------|---------------------------|
| Company blogs (OpenAI, Anthropic, DeepMind, Meta AI, HF, NVIDIA, …) | RSS | none |
| News sites (Verge, TechCrunch, VB, MIT TR, Ars)                    | RSS | none |
| arXiv (cs.AI, cs.CL, cs.LG, cs.CV, stat.ML)                         | Atom | none |
| Reddit (r/MachineLearning, r/LocalLLaMA, r/OpenAI, …)              | `.rss` | none |
| Hacker News (AI-filtered)                                          | Algolia API | none |
| Bluesky (LeCun, Karpathy, Simon Willison, …)                       | public AT proto | none |
| **X/Twitter**                                                      | RSSHub self-host | see `scripts/setup_rsshub.md` |

LinkedIn has no free viable option — skipped.

## Setup

```bash
cd ai-news-tracker
bash scripts/install.sh        # runs uv sync + init DB
cp .env.example .env           # then add your key(s)
```

### Choose a classifier provider

Edit `config.yaml`:

```yaml
provider: anthropic        # or "openai"
models:
  anthropic: claude-haiku-4-5-20251001
  openai:    gpt-5-mini
```

Then drop the matching key in `.env`:
- `ANTHROPIC_API_KEY=sk-ant-...` (get one at console.anthropic.com)
- `OPENAI_API_KEY=sk-proj-...` (get one at platform.openai.com/api-keys)

You only need the key for the provider you picked.

### First run — collect & classify
```bash
source .venv/bin/activate
python scheduler.py
```

### Start web UI
```bash
bash scripts/run_web.sh
# visit http://127.0.0.1:8765
```

### Enable 3h auto-refresh (launchd)
```bash
bash scripts/install_launchd.sh
```

### Add X/Twitter (optional)
Follow `scripts/setup_rsshub.md`, then edit `config.yaml`:
```yaml
rsshub_url: "http://localhost:1200"
```

## Operation

- Runs every 3h. Each run collects all sources, dedupes by URL,
  classifies new items with Claude Haiku (~$0.05–0.15 / run).
- Web UI groups by **importance** (🔥 Major / ⭐ Notable / 📰 Routine)
  and **topic tab**, with latest-first ordering and a 14-day volume
  sparkline + today's count.
- Time window selector: 24h / 48h / 72h / 1 week.

## Files

```
ai-news-tracker/
├── config.yaml           # feeds, subs, handles, model, lookback
├── scheduler.py          # orchestrator (run every 3h)
├── classifier.py         # Claude-based topic + importance
├── collectors/           # rss, arxiv, reddit, hn, bluesky, x
├── storage/db.py         # SQLite
├── web/app.py            # FastAPI dashboard
├── web/templates/        # Jinja2
├── web/static/           # CSS
├── scripts/
│   ├── install.sh
│   ├── install_launchd.sh
│   ├── run_web.sh
│   ├── com.ainews.tracker.plist
│   └── setup_rsshub.md
├── data/news.db          # (created on first run)
└── logs/                 # scheduler + launchd logs
```

## Operate

```bash
# manual run
uv run scheduler.py

# tail logs
tail -f logs/scheduler.log

# check last launchd run
launchctl list | grep ainews

# re-classify everything (delete topic column values)
sqlite3 data/news.db "UPDATE items SET topic=NULL;"
uv run scheduler.py

# stop scheduled runs
launchctl unload ~/Library/LaunchAgents/com.ainews.tracker.plist
```

## Costs

Classifier uses whichever provider you set in `config.yaml`. Expected ~$0.05–0.15 per run with the cheap-tier models on either platform (Claude Haiku 4.5, GPT-5 mini, GPT-4o-mini). At 8 runs/day (every 3h) most runs find few new items, so realistic monthly cost is **~$10–25/month** at typical volumes. Monitor on the provider's dashboard.

## Security note

`.env` is `chmod 600` and gitignored. Your API key is local-only. **Rotate
the key you pasted into chat** at console.anthropic.com → API Keys.
