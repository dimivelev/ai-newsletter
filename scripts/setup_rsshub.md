# Setting up RSSHub for X/Twitter (optional)

X/Twitter does not offer a usable free API or RSS, so to collect tweets we
run a local RSSHub instance and point the tracker at it.

## 1. Install Docker Desktop for Mac
https://www.docker.com/products/docker-desktop/

## 2. Get an X auth token (required — X blocks anonymous access)

1. Log in to X in your browser with a **throwaway account** (not your main).
2. Open devtools → Application → Cookies → `x.com`.
3. Copy the value of `auth_token`.

> ⚠️ Using your personal account risks a suspension. Use a throwaway.
> This is a ToS-gray area — we are scraping public tweets for personal use.

## 3. Run RSSHub

```bash
docker run -d --name rsshub --restart=always -p 1200:1200 \
  -e TWITTER_AUTH_TOKEN=<paste_auth_token> \
  diygod/rsshub
```

Verify:
```bash
curl http://localhost:1200/twitter/user/OpenAI | head -40
```

## 4. Point the tracker at it

Edit `config.yaml`:
```yaml
rsshub_url: "http://localhost:1200"
```

## 5. Keep it alive

The `--restart=always` flag makes Docker restart the container on boot.
If tweets stop flowing, the `auth_token` likely expired — grab a fresh one
and `docker rm -f rsshub` then re-run the command above.

## Alternatives

- **Bluesky** (already included, no setup) covers LeCun, Karpathy, Simon
  Willison, and many AI researchers who cross-post.
- Some AI orgs (OpenAI, Anthropic, DeepMind) post all major announcements
  to their blog first — already covered by RSS.
