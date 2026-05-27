# Spec: Local Q&A Assistant (RAG) Feature

This specification details the design for the Local Q&A Assistant / RAG feature (Phase 4) in the AI News Tracker.

## Goal Description
Implement a conversational chatbot drawer inside the dashboard web UI. Users can ask natural language questions about collected news and research papers (e.g. "What LLM models were released this week?"). The assistant uses keyword-matching database queries and recent high-importance entries to feed context to the configured LLM provider (Claude, OpenAI, NIM, or Ollama) and generates fact-based answers with links to the original articles.

## User Review Required
No breaking changes or manual database migrations are required. The changes are fully backward-compatible.

## Open Questions
*None. All requirements have been clarified and approved.*

## Proposed Changes

### Exporter & LLM Component

#### [MODIFY] [classifier.py](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/classifier.py)
*   Add a public bridge method `generate_response(system: str, user: str) -> str` to the `BaseClassifier` base class to leverage existing LLM connection, retry, and client management logic.

---

### Backend Component

#### [NEW] [chat.py](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/storage/chat.py)
Create a new module handling context retrieval and answering:
*   `extract_keywords(query: str) -> list[str]`: Helper to filter out stop words and extract searchable keywords from query queries.
*   `retrieve_context(query: str) -> list[sqlite3.Row]`:
    *   Find the top 25 matches matching keywords in title, TLDR, and summary fields.
    *   Find the top 25 most recent Major & Notable items from the last 7 days.
    *   Combine, deduplicate by URL, and return up to 40 items.
*   `answer_question(query: str, chat_history: list[dict], cfg: dict) -> str`:
    *   Fetch context items using `retrieve_context`.
    *   Format context items into a text context block.
    *   Construct a RAG system prompt with citation formatting instructions.
    *   Fetch response from the configured LLM using `classifier.get_classifier(cfg)`.

#### [MODIFY] [app.py](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/web/app.py)
*   Add endpoint `POST /api/chat`:
    *   Accepts `{"messages": [{"role": "user", "content": "..."}]}`.
    *   Extracts query, calls `chat.answer_question(query, chat_history, cfg)` and returns `{"content": "..."}`.

---

### Frontend Component

#### [MODIFY] [index.html](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/web/templates/index.html)
*   Add float toggle chat button in the bottom right corner of the dashboard viewport.
*   Add chat drawer panel layout (`#chat-drawer`):
    *   Drawer header with clear history (🗑️) and close (✕) button.
    *   Scrollable message area.
    *   Input text box with Send button.
*   Add JavaScript to:
    *   Toggle `.open` class on drawer slide-in / slide-out.
    *   Render message bubbles for user and assistant.
    *   Submit conversation lists to `/api/chat`.
    *   Append typing indicators.
    *   Convert markdown bold, italic, and `[Title](URL)` tags into active HTML links inline.

#### [MODIFY] [style.css](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/web/static/style.css)
*   Add styling for `.chat-drawer` panel (right side fixed positioning, shadow, border rules, overflow scrolling, open state animations).
*   Add styling for `.chat-toggle-btn` float button (shape, color accents, hover transitions).
*   Add message bubble styling rules for `.msg-user` and `.msg-ai`.
*   Include mobile width query constraints (scale drawer to full screen on screens <= 900px wide).

---

## Verification Plan

### Automated Tests
We will create a new test suite [test_chat.py](file:///C:/Users/divelev/Desktop/svaleni/ai-news-tracker/tests/test_chat.py):
*   Verify keyword extractor filters stopwords.
*   Verify `retrieve_context` returns matching articles.
*   Verify `POST /api/chat` route processes requests and yields LLM answers.

### Manual Verification
*   Open `http://127.0.0.1:8765`.
*   Verify clicking the float button slides the drawer open.
*   Ask questions like "What are the latest releases?" and verify the AI replies using context articles with active markdown citation links.
*   Click trash icon to verify chat log clearing.
