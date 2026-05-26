# Design: GitHub Actions Automation & Pages Deployment with SQLite Persistence

This document details the architecture and implementation plan for scheduling the AI News Tracker collector using GitHub Actions, persisting the database within the repository, and hosting the dashboard on GitHub Pages.

## Problem Statement & Context

We want to automate the local AI News Tracker so it runs without human intervention.
* The orchestrator script ([scheduler.py](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/scheduler.py)) runs every 3 hours to collect and classify news.
* We want to run this process on a schedule via GitHub Actions.
* The runner is ephemeral, meaning database changes to `data/news.db` will be lost at the end of a job.
* We need a zero-maintenance, zero-cost dashboard web page hosted on GitHub Pages that showcases the latest news.

## Proposed Design: Approach A (Modern Pages Deploy + Git Commit DB)

We will configure GitHub Actions to run the orchestrator, commit the updated `data/news.db` SQLite database back to the repo, compile the data into a static HTML file via [scripts/export_html.py](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/scripts/export_html.py), and deploy it directly to GitHub Pages.

### Component Changes

#### 1. [MODIFY] [.gitignore](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/.gitignore)
By default, `.gitignore` excludes `data/*.db`. We need to explicitly allow tracking `data/news.db` while continuing to ignore logs, journal files, and `.env` files.
We will modify the `.gitignore` to un-ignore `data/news.db`:
```diff
 .env
-data/*.db
+data/*.db-journal
+!data/news.db
 logs/*.log
```

#### 2. [NEW] [.github/workflows/tracker-cron.yml](file:///.github/workflows/tracker-cron.yml)
We will create a GitHub Actions workflow that implements the scheduling, database commit, and Pages deployment steps.

```yaml
name: Collect News and Deploy Pages

on:
  schedule:
    # Run every 3 hours
    - cron: '0 */3 * * *'
  # Allow manual trigger from the Actions tab
  workflow_dispatch:

permissions:
  contents: write
  pages: write
  id-token: write

concurrency:
  group: "pages-deploy"
  cancel-in-progress: false

jobs:
  collect-and-deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0 # Fetch all history for Git push

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version-file: ".python-version"

      - name: Install dependencies
        run: uv sync --frozen

      - name: Run collector & classifier
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          uv run scheduler.py

      - name: Commit database changes
        run: |
          git config --local user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git config --local user.name "github-actions[bot]"
          if [ -f "data/news.db" ]; then
            git add data/news.db
            if ! git diff --cached --quiet; then
              git commit -m "chore: update news database [skip ci]"
              git push
            else
              echo "No database changes to commit."
            fi
          else
            echo "Database file data/news.db not found."
          fi

      - name: Generate static HTML
        run: |
          uv run scripts/export_html.py
          mkdir -p _site
          cp export/dispatch.html _site/index.html

      - name: Upload Pages artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: _site

      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

---

## Verification Plan

### Automated Tests / Validation
* We will push the workflow file to GitHub and manually trigger it using `workflow_dispatch`.
* Verify that:
  1. Dependencies install successfully via `uv`.
  2. The scheduler executes correctly (mock/empty runs if credentials aren't yet added, or full run once secrets are configured).
  3. Git committing runs cleanly and pushes `data/news.db` back to the repository.
  4. The Pages build succeeds and uploads the static artifact.
  5. The site is live on `<username>.github.io/<repo-name>/`.

### Manual Actions Needed by User
* Configure the GitHub Repository Secrets:
  * `ANTHROPIC_API_KEY` (if using Claude)
  * `OPENAI_API_KEY` (if using OpenAI)
* Enable GitHub Pages on your repository settings:
  * Navigate to **Settings** -> **Pages**.
  * Under **Build and deployment** -> **Source**, select **GitHub Actions**.
