"""Collectors for AI news sources.

Each collector exposes a `collect()` function returning a list of dicts:
    {
      "source": "...",        # display label, e.g. "OpenAI"
      "source_type": "...",   # rss | arxiv | reddit | bluesky | x | hn
      "url": "...",
      "title": "...",
      "summary": "...",
      "author": "...",
      "published_at": "ISO-8601 UTC",
      "topic": "...",         # topic hint (may be overwritten by classifier)
    }
"""
