# Spec: Daily/Weekly Digest Exporter Feature

This specification details the design for the Daily/Weekly Digest Exporter (Phase 3) in the AI News Tracker.

## Goal Description
Provide a mechanism to compile and export recent AI news (Daily/Weekly) into highly-readable Markdown (.md) and HTML (.html) formats, filtering for high-signal content (Major & Notable items). The feature is accessible via both a CLI script (for automated exports) and direct web download buttons on the dashboard.

## User Review Required
No breaking changes or manual migrations are required. The changes are fully backward-compatible.

## Open Questions
*None. All requirements have been clarified and approved.*

## Proposed Changes

### Database & Exporter Component

#### [NEW] [exporter.py](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/storage/exporter.py)
Create a unified core module containing the formatting logic:
*   `generate_markdown_digest(since_hours: int, min_importance: int, topic: str, q: Optional[str] = None, sources: Optional[list[str]] = None) -> str`:
    *   Queries items matching parameters from the database.
    *   Groups them by importance: Major Announcements (3) and Notable News (2) (Routine (1) is included only if `min_importance=1`).
    *   Constructs a formatted Markdown document containing: title, source, publication date/time, summary, TL;DR, and classification reason.
*   `generate_html_digest(since_hours: int, min_importance: int, topic: str, q: Optional[str] = None, sources: Optional[list[str]] = None) -> str`:
    *   Uses a dedicated newsletter Jinja2 template (`digest_template.html`).
    *   Renders a styled standalone HTML newsletter output.

---

### Backend Component

#### [NEW] [digest_template.html](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/web/templates/digest_template.html)
Define an email-safe, responsive, standalone HTML template with custom CSS styling suitable for desktop and mobile viewing.

#### [MODIFY] [app.py](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/web/app.py)
*   Add endpoint `GET /api/export/digest`:
    *   Parameters: `format: str`, `hours: int = 168`, `topic: str = "All"`, `q: str = ""`, `sources: str = ""`, `min_importance: int = 2`.
    *   Generates a digest string using `storage.exporter`.
    *   Returns a FastAPI `Response` with headers `Content-Disposition: attachment; filename=digest_YYYY-MM-DD.<ext>` and corresponding MIME types.

---

### CLI Component

#### [NEW] [export_digest.py](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/scripts/export_digest.py)
Create a new CLI tool:
*   Parses arguments: `--hours`, `--min-importance`, `--topic`, `--format` (`markdown`, `html`, or `both`), `--out-dir` (defaults to `export/`).
*   Writes output files to the specified directory.

---

### Frontend Component

#### [MODIFY] [index.html](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/web/templates/index.html)
*   Add an export utilities button panel in the `.masthead` header under the edition metadata subtitle:
    *   Link to `/api/export/digest?format=markdown&hours={{ hours }}&topic={{ active_topic }}&q={{ q }}&sources={{ sources }}`.
    *   Link to `/api/export/digest?format=html&hours={{ hours }}&topic={{ active_topic }}&q={{ q }}&sources={{ sources }}`.

#### [MODIFY] [style.css](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/web/static/style.css)
*   Add styling classes for `.export-actions` and `.btn-export` links.
*   Accents: slate border, low-profile monospace font, and a transition to violet hover effects.

---

## Verification Plan

### Automated Tests
We will create a new test suite [test_exporter.py](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/tests/test_exporter.py):
*   Verify that `generate_markdown_digest` produces valid markdown with correct groups.
*   Verify that `generate_html_digest` correctly compiles matching items.
*   Verify the `/api/export/digest` endpoint returns the files with correct headers.

### Manual Verification
*   Start the web server locally and open `http://127.0.0.1:8765`.
*   Click "Download Markdown Digest" and verify the file compiles and downloads.
*   Click "Download HTML Digest" and verify the file compiles and downloads.
*   Run the script `uv run python scripts/export_digest.py --hours 24 --format both` and check that files are written correctly in `export/`.
