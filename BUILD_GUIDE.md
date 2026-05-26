# How I built my own AI news intelligence dashboard in an afternoon

*A practical, end-to-end walkthrough for building a self-hosted AI news aggregator that classifies stories by importance using Claude — and a clean web dashboard you can keep open all day.*

---

## Why I built this

Every morning I open ten tabs to keep up with AI: arXiv, Hacker News, the OpenAI / Anthropic / DeepMind blogs, MIT Tech Review, Reddit, LinkedIn, X, the Bluesky researcher feed. Most of it is noise. The 5% that matters is buried under launches, opinion takes, and recycled hot-takes.

I wanted one screen — sorted by what actually matters — that refreshes itself while I work.

So I built **The AI Dispatch** — a local Python app that:

- Pulls from ~40 AI sources (RSS, arXiv, Reddit, Hacker News, Bluesky, optionally X)
- Asks an LLM (your choice — **Claude Haiku** or **GPT-5 mini**) to classify each item by topic and importance (Major / Notable / Routine)
- Stores everything in SQLite
- Renders a clean web dashboard at `localhost:8765`
- Refreshes automatically every 3 hours via macOS `launchd`
- Costs me about **$15/month** in API credits

It's about ~1,200 lines of Python total, **provider-agnostic** so you can plug in whichever LLM you have a key for. You can build the same thing in an afternoon.

In this article I'll walk through every step. If you'd rather skip to the result, the snapshot HTML I exported is attached to this newsletter — you can open it offline and click around.

---

## The honest stack

```
collectors/   # one Python module per source
classifier.py # batches items to Claude for triage
storage/      # SQLite, ~80 lines
scheduler.py  # the orchestrator — runs every 3h
web/          # FastAPI dashboard, ~50 lines + Jinja template
```

Free tools, no account creation other than Anthropic's. Total third-party services: **one** (the Claude API).

**A note on social platforms.** I researched this carefully. As of 2026:

- **Reddit** — works free via the public JSON endpoint (with a User-Agent header).
- **Hacker News** — Algolia's HN search API is free, no auth.
- **Bluesky** — public AT Protocol, no auth needed for public posts.
- **X / Twitter** — free API was crippled in 2023. Only path is a self-hosted RSSHub instance with a throwaway account's cookie. ToS-gray. Most AI researchers cross-post to Bluesky now anyway.
- **LinkedIn** — no viable free path. Don't try. Company blogs cover ~90% of what matters.
- **arXiv, company blogs** — RSS is plentiful and stable.

If you stick to the green-light list (everything except X and LinkedIn), you have a clean, fully legal, fully free pipeline.

---

## Step 1 — Set up your project

```bash
mkdir ai-news-tracker && cd ai-news-tracker
python3 -m venv .venv && source .venv/bin/activate

# requirements.txt
cat > requirements.txt <<EOF
anthropic>=0.40.0
feedparser>=6.0.11
httpx>=0.27.0
arxiv>=2.1.3
python-dotenv>=1.0.1
pyyaml>=6.0.2
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
jinja2>=3.1.4
beautifulsoup4>=4.12.3
lxml>=5.3.0
python-dateutil>=2.9.0
tenacity>=9.0.0
EOF

pip install -r requirements.txt
```

Pick a provider — three options, including one that's **completely free with no API key**:

| Provider | Cost | Key needed | Setup |
|---|---|---|---|
| **Anthropic** (Claude) | ~$10–25/mo | yes | console.anthropic.com → Settings → API Keys |
| **OpenAI** | ~$10–25/mo | yes | platform.openai.com/api-keys |
| **Ollama** (local LLM) | $0 | no | install at ollama.com, then `ollama pull llama3.2` |

If you're trying this on the side and don't want to add a paid subscription, **start with Ollama**. The classification quality is somewhat lower than Claude Haiku or GPT-5 mini, but for triage at this scale (Major / Notable / Routine) it's good enough — and it runs entirely on your laptop with no rate limits and no spend.

For the paid options, drop the key in `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
# or
OPENAI_API_KEY=sk-proj-...
```

Then `chmod 600 .env` and add `.env` to `.gitignore`.

---

## Step 2 — Define your sources in YAML

I keep all the knobs in `config.yaml` so I never have to touch Python to add a feed or switch providers:

```yaml
provider: anthropic        # anthropic | openai | ollama
models:
  anthropic: claude-haiku-4-5-20251001
  openai:    gpt-5-mini
  ollama:    llama3.2

lookback_hours: 24
max_items_per_source: 30

topics:
  - Frontier Models
  - Research Papers
  - Chips & Hardware
  - Tools & Infra
  - Policy & Regulation
  - Applications
  - Social Buzz

rss_feeds:
  - { name: "OpenAI",         url: "https://openai.com/news/rss.xml",       topic: "Frontier Models" }
  - { name: "Anthropic",      url: "https://www.anthropic.com/news/rss.xml", topic: "Frontier Models" }
  - { name: "Google DeepMind",url: "https://deepmind.google/blog/rss.xml",   topic: "Frontier Models" }
  - { name: "Hugging Face",   url: "https://huggingface.co/blog/feed.xml",   topic: "Tools & Infra" }
  - { name: "NVIDIA Blog",    url: "https://blogs.nvidia.com/feed/",         topic: "Chips & Hardware" }
  # ... add more

arxiv_categories: [cs.AI, cs.CL, cs.LG, cs.CV, stat.ML]

reddit_subs:
  - { name: "r/MachineLearning", sub: "MachineLearning", topic: "Research Papers" }
  - { name: "r/LocalLLaMA",      sub: "LocalLLaMA",      topic: "Tools & Infra" }
  - { name: "r/OpenAI",          sub: "OpenAI",          topic: "Frontier Models" }

bluesky_handles:
  - karpathy.bsky.social
  - simonw.bsky.social
  - emilymbender.bsky.social
```

The `topic` is a hint that I let the classifier override based on actual content.

---

## Step 3 — Write your collectors

Each collector exports one function — `collect()` — returning a list of dicts in this exact shape:

```python
{
  "source":       "OpenAI",
  "source_type":  "rss",
  "url":          "https://...",   # used as dedupe key
  "title":        "...",
  "summary":      "...",
  "author":       "...",
  "published_at": "2026-05-08T09:00Z",   # ISO 8601 UTC
  "topic":        "Frontier Models",
}
```

The simplest is RSS:

```python
# collectors/rss.py
import feedparser
from dateutil import parser as dateparser
from datetime import timezone

def collect(feeds, max_per_feed=30):
    items = []
    for feed in feeds:
        parsed = feedparser.parse(feed["url"], request_headers={
            "User-Agent": "ai-news-tracker/1.0"
        })
        for entry in parsed.entries[:max_per_feed]:
            items.append({
                "source":       feed["name"],
                "source_type":  "rss",
                "url":          entry.get("link"),
                "title":        entry.get("title", "").strip(),
                "summary":      entry.get("summary", "")[:600],
                "author":       entry.get("author", ""),
                "published_at": dateparser.parse(entry.get("published") or entry.get("updated"))
                                    .astimezone(timezone.utc).isoformat(),
                "topic":        feed.get("topic", ""),
            })
    return items
```

For arXiv, use the official `arxiv` package — it handles the 3-second rate limit for you. For Hacker News, hit `hn.algolia.com/api/v1/search_by_date` with a query like `AI OR LLM OR AGI` and a points threshold. For Reddit, the JSON endpoint at `/r/<sub>/new.json` works without auth as long as you send a `User-Agent`. For Bluesky, the public AT Protocol API doesn't even need a key:

```python
# collectors/bluesky.py
import httpx

API = "https://public.api.bsky.app/xrpc"

def collect(handles, lookback_hours=24, max_per_handle=30):
    items = []
    for handle in handles:
        did = httpx.get(f"{API}/com.atproto.identity.resolveHandle",
                        params={"handle": handle}).json()["did"]
        feed = httpx.get(f"{API}/app.bsky.feed.getAuthorFeed",
                         params={"actor": did, "limit": max_per_handle}).json()["feed"]
        for entry in feed:
            post = entry["post"]
            record = post["record"]
            # ... normalize and append
    return items
```

This is the entire moat. Five collectors, ~250 lines total.

---

## Step 4 — Wire up SQLite

```python
# storage/db.py
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "news.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    source_type     TEXT NOT NULL,
    url             TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    summary         TEXT,
    author          TEXT,
    published_at    TEXT NOT NULL,
    collected_at    TEXT NOT NULL,
    topic           TEXT,
    importance      INTEGER,
    importance_why  TEXT,
    tldr            TEXT
);
CREATE INDEX IF NOT EXISTS idx_published ON items(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_topic     ON items(topic);
CREATE INDEX IF NOT EXISTS idx_imp       ON items(importance DESC);
"""
```

The `UNIQUE(url)` constraint is the key — it gives you free deduplication across runs. Insert with `INSERT OR IGNORE` and you'll never double-count.

---

## Step 5 — Add an LLM to triage

This is where it gets fun. After insertion, I send the new items to the LLM in batches of 10 with this system prompt:

```
You are an AI news triage analyst. For each item you receive,
output a JSON object with:
  "topic": one of {topics}
  "importance": 1 (routine), 2 (notable), 3 (major breakthrough)
  "why": <= 15 words explaining the importance
  "tldr": <= 25-word plain-English summary

Rules for importance:
 - 3 = new major model release, major funding/acquisition,
       regulation with teeth, breakthrough benchmark, big chip-supply shift
 - 2 = notable partnership, second-tier product update,
       strong research paper, meaningful policy debate
 - 1 = incremental, rumor, opinion piece, minor blog post

Return ONLY a JSON array, one object per input item, in input order.
```

I built it provider-agnostic so I (or you) can switch between Anthropic and OpenAI by editing one line in `config.yaml`. The pattern is a tiny abstract base class with one method per provider:

```python
class BaseClassifier(ABC):
    @abstractmethod
    def _call(self, system, user) -> str: ...

    def classify_batch(self, items, topics, batch_size=10):
        # batches the items, calls _call, parses JSON — same for both providers

class AnthropicClassifier(BaseClassifier):
    def __init__(self, model):
        from anthropic import Anthropic
        self.client = Anthropic()
        self.model = model

    def _call(self, system, user):
        resp = self.client.messages.create(
            model=self.model, max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text

class OpenAIClassifier(BaseClassifier):
    def __init__(self, model):
        from openai import OpenAI
        self.client = OpenAI()
        self.model = model

    def _call(self, system, user):
        resp = self.client.chat.completions.create(
            model=self.model, max_tokens=4096,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content

class OllamaClassifier(OpenAIClassifier):
    """Free local LLM via Ollama's OpenAI-compatible API."""
    def __init__(self, model, base_url="http://localhost:11434/v1"):
        from openai import OpenAI
        self.client = OpenAI(api_key="ollama", base_url=base_url)
        self.model = model

def get_classifier(cfg):
    provider = cfg.get("provider", "anthropic")
    model = cfg["models"][provider]
    return {"anthropic": AnthropicClassifier,
            "openai":    OpenAIClassifier,
            "ollama":    OllamaClassifier}[provider](model)
```

Ollama exposes an OpenAI-compatible API on `localhost:11434`, so the local-LLM path is one tiny subclass.

The same prompt works for both — they're roughly equivalent at this kind of structured triage at the cheap tier (Haiku 4.5 ↔ GPT-5 mini ↔ GPT-4o-mini). Over a month at 8 refreshes a day, my cost is **$12–18** on either provider.

**The single most important thing I did**: be specific in the rubric. My first version classified everything as "Notable." Once I added the negative examples (`opinion piece = 1, rumor = 1`), the distribution flipped to ~85% Routine, ~14% Notable, ~1% Major — which is much closer to reality.

---

## Step 6 — Build the dashboard

FastAPI + Jinja2. Server-rendered, no JavaScript needed.

```python
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="web/templates")

@app.get("/")
def index(request: Request, topic: str = "All", hours: int = 168):
    rows = db.fetch_items(topic=topic, since_hours=hours, limit=500)
    grouped = group_by_importance(rows)
    return templates.TemplateResponse(request, "index.html", {
        "grouped": grouped,
        "topics": load_topics(),
        "active_topic": topic,
        "hours": hours,
        "daily": db.daily_counts(days=14),
        "topic_cnt": db.topic_counts(since_hours=hours),
        "last_run": db.last_run(),
    })
```

That's the entire dashboard. ~50 lines including imports.

The template groups items by importance, renders a 14-day volume sparkline, and gives you tabs per topic. I went through three design iterations to land on the lighter, serif-driven look — see the snapshot attached to this newsletter for the final version.

---

## Step 7 — Schedule it (macOS)

I use `launchd` because it survives reboots and doesn't need a daemon process running while my laptop's idle. Two plist files in `~/Library/LaunchAgents/`:

**`com.ainews.tracker.plist`** — collection runs every 3 hours:

```xml
<key>StartInterval</key><integer>10800</integer>
<key>RunAtLoad</key><true/>
<key>ProgramArguments</key>
<array>
    <string>/path/to/.venv/bin/python</string>
    <string>/path/to/scheduler.py</string>
</array>
```

**`com.ainews.web.plist`** — dashboard always on:

```xml
<key>KeepAlive</key><true/>
<key>RunAtLoad</key><true/>
<key>ProgramArguments</key>
<array>
    <string>/path/to/.venv/bin/python</string>
    <string>-m</string><string>uvicorn</string>
    <string>web.app:app</string>
    <string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>8765</string>
</array>
```

`launchctl load ~/Library/LaunchAgents/com.ainews.*.plist` and you're done. No supervisor, no Docker, no systemd, no cron. macOS owns these processes for as long as you're logged in.

On Linux: substitute systemd timer + service unit. On Windows: Task Scheduler + a service wrapper. Same idea.

---

## Step 8 — Make it portable

The dashboard runs at `localhost:8765` on my machine. To share an issue (like this one), I have an exporter that:

1. Reads the live SQLite database
2. Inlines the entire CSS into a `<style>` tag
3. Renders the template with `mode='export'`, which swaps server-rendered tab links for `<button>` elements with a tiny vanilla-JS filter
4. Writes a single self-contained `dispatch.html` to `export/`

```python
# scripts/export_html.py
from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader("web/templates"))
html = env.get_template("index.html").render(
    mode="export",
    inline_css=Path("web/static/style.css").read_text(),
    grouped=...,
    # same context as live route
)
Path("export/dispatch.html").write_text(html)
```

The result is a ~750 KB HTML file you can attach to a LinkedIn post, e-mail to a colleague, or host on any static server. No backend, no API keys baked in (I checked with `grep -i "sk-ant" export/dispatch.html` — clean).

---

## What I learned

**The classifier matters more than the collectors.** My collectors took an afternoon. My classifier rubric took a week of tuning. Importance is subjective — what's "major" depends on what you care about. Spend time on the prompt.

**Source weight beats source quantity.** I'd rather have 8 well-curated sources than 80 noisy ones. Adding TechCrunch's full feed costs me nothing in API spend but a lot in noise. Curate aggressively.

**SQLite is more than enough.** For 1,000 items/week and one user, SQLite is faster, simpler, and more reliable than anything else. The whole DB after a month is 12 MB.

**Don't fight LinkedIn or X.** Their anti-scraping measures changed three times in the last two years. Bluesky has the same researchers and a real public API. Move on.

**Refresh cadence is a personal call.** I do 3 hours. Some friends do 1 hour. The cost difference is negligible (most refreshes find <30 new items). The signal-to-noise difference is real — refreshing too often gives you the dopamine of news but breaks your concentration. Find your rhythm.

---

## What's next

Things I'm planning to add:

- **Slack digest** — once a day, post the Major + Notable items to a private channel.
- **Email summary** — a Sunday weekly digest by topic, rendered to plain text.
- **Custom interest weighting** — let me upweight certain authors / orgs without forking the prompt.
- **A second classifier pass** — flag items where multiple sources covered the same story (cross-source dedup).
- **Vector search** — "what was that paper about long-context attention from last month?"

If you want to build this yourself, I'm happy to share the full repo. Drop me a message on LinkedIn.

If you found this useful, consider subscribing to **The AI Value Playbook** — a weekly newsletter where I write about shipping AI that actually creates business value, with practical builds like this one.

— *Lina Varbanova*

[Subscribe to The AI Value Playbook →](https://www.linkedin.com/newsletters/the-ai-value-playbook-7457782473419026432/)
[Connect on LinkedIn →](https://www.linkedin.com/in/lina-varbanova-mba-12a89b17/)
