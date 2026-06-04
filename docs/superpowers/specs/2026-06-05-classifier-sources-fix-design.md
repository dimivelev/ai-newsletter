# Fix Classifier + Add Sources Design

## Problem
1. **Classifier not running** — `config.yaml` set to `provider: nim` but `NVIDIA_API_KEY` was not passed to the GitHub Actions workflow. All runs since ~May 16 collected raw items but failed at classification (`NVIDIA_API_KEY not set in env`).
2. **Classifier prompt too conservative** — criteria for importance 2/3 were too strict ("breakthrough", "senior safety incident"), so even when the classifier ran, it defaulted to 1. Also no distribution guidance.
3. **Missing sources** — no Mistral AI, Apple ML Research, TLDR AI, or The Neuron in the RSS feeds.

## Changes

### 1. Workflow fix (tracker-cron.yml)
- Added `NVIDIA_API_KEY: ${{ secrets.NVIDIA_API_KEY }}` to the collector step's env block.

### 2. Classifier prompt (classifier.py)
- Added expected distribution guidance: ~60% routine, 30% notable, 10% major.
- Framed the feed as "high-signal AI news" to set context.
- Broadened "notable" (2) to include product updates, research papers, benchmark results, interesting analysis.
- Narrowed "routine" (1) to mostly noise/incremental/speculative content.
- Kept "major" (3) criteria largely the same but slightly broadened.

### 3. New RSS sources (config.yaml)
- Added Mistral AI blog (Frontier Models)
- Added Apple ML Research blog (Research Papers)
- Added TLDR AI newsletter (Applications)
- Added The Neuron newsletter (Applications)

## Remaining work
Once everything is deployed, the next run will:
1. Collect items normally
2. Classify them successfully with the new prompt
3. Re-classify backlog unclassified items (via `fetch_unclassified` in `scheduler.py`)
