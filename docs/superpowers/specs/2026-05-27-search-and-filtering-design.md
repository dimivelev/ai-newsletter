# Spec: Advanced Search & Multi-Filtering Feature

This specification details the design for the Advanced Search & Multi-Filtering feature (Phase 2) in the AI News Tracker.

## Goal Description
Allow users to query news items using search terms matching the title, TLDR, or summary, and filter news items by specific source types (e.g. RSS feed, arXiv, Reddit, Bluesky, Hacker News, X/Twitter) using multi-select pills.

## User Review Required
No breaking changes or manual migrations are required. The changes are fully backward-compatible.

## Open Questions
*None. All requirements have been clarified and approved.*

## Proposed Changes

### Database Component

#### [MODIFY] [db.py](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/storage/db.py)
We will update database functions to support dynamic SQL clause building for filtering:
*   `fetch_items(topic, since_hours, limit, q, sources)`
*   `fetch_bookmarked_items(q, sources)`
*   `topic_counts(since_hours, q, sources)`
*   `count_bookmarks(q, sources)`

For the filters:
*   **Search Filter**: Append `AND (items.title LIKE ? OR items.tldr LIKE ? OR items.summary LIKE ?)` if `q` is specified.
*   **Source Type Filter**: Append `AND items.source_type IN (?, ?, ...)` if a list of `sources` is specified.

---

### Backend Component

#### [MODIFY] [app.py](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/web/app.py)
*   Update `index` controller to accept optional query string parameters `q: str = ""` and `sources: str = ""`.
*   Parse `sources` into a list: `active_sources = sources.split(",") if sources else []`.
*   Pass `q` and `active_sources` to `db.fetch_items()`, `db.fetch_bookmarked_items()`, `db.topic_counts()`, and `db.count_bookmarks()`.
*   Expose `q` and `sources` (as comma-separated string) to the Jinja template context so the frontend can populate inputs and active pill states.

---

### Frontend Component

#### [MODIFY] [index.html](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/web/templates/index.html)
*   Insert a **Search & Filter Panel** form below the masthead and above the stats strip.
*   The panel will contain:
    *   A search box input with clear text ("✕") button.
    *   A row of checkable source pills (RSS, arXiv, Reddit, HN, Bluesky, X).
    *   A hidden input `<input type="hidden" name="sources" id="sources-input">` containing comma-separated active sources.
*   Update active topic link URLs to preserve the active search query (`q`) and source list (`sources`) parameters when navigation tabs are clicked.
*   Add client-side JavaScript to:
    *   Initialize pills from the active URL query parameters.
    *   Toggle pill active classes and update the hidden sources input on click, submitting the search form immediately.
    *   Submit the search query only on Form submit (Enter key press or clicking search/magnifier button).

#### [MODIFY] [style.css](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/web/static/style.css)
*   Create styles for `.search-filter-panel`, `.search-box`, and `.source-pills`.
*   Add styling for active and hover states of the pills (using `var(--violet)`, `var(--violet-soft)` backgrounds).
*   Ensure responsive layout for the search and filtering controls on mobile screens.

---

## Verification Plan

### Automated Tests
We will add new tests to [test_bookmarks.py](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/tests/test_bookmarks.py) or a new test suite:
*   Verify SQL dynamic queries for `fetch_items` and `fetch_bookmarked_items` with query strings and source list parameters.
*   Verify tab count matching logic under active filters.
*   Verify FastAPI route handles `q` and `sources` correctly and returns matching items.

### Manual Verification
*   Start the web server locally and open `http://127.0.0.1:8765`.
*   Test typing in the search bar and pressing Enter. Verify only items matching the query are displayed.
*   Test clicking one or more source type pills (e.g. arXiv + RSS). Verify the list updates to only show these source types.
*   Combine search queries (e.g. "Llama") with source filters (e.g. arXiv). Verify results only show arXiv papers matching "Llama".
*   Navigate to the "Bookmarked" tab, perform search queries, and toggle source pills. Verify filtering works within bookmarked items.
*   Verify tab badges update counts based on active search queries and source type filters.
