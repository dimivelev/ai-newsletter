# Spec: Bookmarking & "Read Later" Feature

This specification details the design for the Bookmarking & "Read Later" feature (Phase 1) in the AI News Tracker.

## Goal Description
Allow users to flag news items they find interesting and save them to a persistent dashboard tab. This allows users to read articles later without them expiring from the main feed when the active lookback window (e.g., 24h, 48h, 72h, 1 week) passes.

## User Review Required
No major breaking changes are expected. The database schema will be extended with a new `bookmarks` table, which is fully backward-compatible.

## Open Questions
*None. All requirements have been clarified and approved.*

## Proposed Changes

### Database Component

#### [NEW] `bookmarks` Table
We introduce a new table in the database schema defined in [db.py](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/storage/db.py):
```sql
CREATE TABLE IF NOT EXISTS bookmarks (
    item_id    INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
);
```

#### [MODIFY] [db.py](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/storage/db.py)
We will add the following helper functions:
*   `add_bookmark(item_id: int) -> None`: Inserts a record into `bookmarks`.
*   `remove_bookmark(item_id: int) -> None`: Deletes a record from `bookmarks` by `item_id`.
*   `fetch_bookmarked_items() -> list[sqlite3.Row]`: Queries `items` joined with `bookmarks` ordered by `bookmarks.created_at DESC`.
*   `fetch_items()`: Updated to `LEFT JOIN bookmarks ON items.id = bookmarks.item_id` and select `(bookmarks.item_id IS NOT NULL) AS is_bookmarked`.
*   `count_bookmarks() -> int`: Returns the total number of bookmarked items.

---

### Backend Component

#### [MODIFY] [app.py](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/web/app.py)
*   **New API endpoints**:
    *   `POST /api/bookmarks/{item_id}`: Call `db.add_bookmark(item_id)`.
    *   `DELETE /api/bookmarks/{item_id}`: Call `db.remove_bookmark(item_id)`.
*   **Web routes update**:
    *   Pass the output of `db.count_bookmarks()` as `bookmark_count` to templates.
    *   If `topic == "Bookmarked"`, fetch bookmarked items using `db.fetch_bookmarked_items()` and bypass the time-window query restrictions.

---

### Frontend Component

#### [MODIFY] [index.html](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/web/templates/index.html)
*   Add a "Bookmarked" tab to the topic navigation bar, showing the total bookmarks count badge.
*   Add a toggle button (☆ / ★) next to each item title.
*   Inject a script to handle:
    *   Sending asynchronous API requests when clicking the bookmark button.
    *   Updating button styles immediately on success.
    *   Animating item removal (fading out and sliding up) if toggled off while on the "Bookmarked" tab.

#### [MODIFY] [style.css](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/web/static/style.css)
*   Style the bookmark star button (cursor, hover scaling, amber-gold `#f59e0b` fill when active).
*   Add keyframe animations for the smooth fade-out and collapse of unbookmarked items on the Bookmarked tab.

---

## Verification Plan

### Automated Tests
We will write unittest/pytest test files to verify:
*   Database methods: `add_bookmark`, `remove_bookmark`, and `fetch_bookmarked_items`.
*   FastAPI endpoints: `POST /api/bookmarks/{item_id}` and `DELETE /api/bookmarks/{item_id}`.

### Manual Verification
*   Launch the FastAPI dashboard (`uv run uvicorn web.app:app --port 8765 --reload`).
*   Verify clicking bookmark toggles states and saves items across page refreshes.
*   Verify that the "Bookmarked" tab ignores the active time window filter and holds items indefinitely.
*   Verify that un-bookmarking an item while inside the "Bookmarked" tab causes it to fade out and slide shut.
