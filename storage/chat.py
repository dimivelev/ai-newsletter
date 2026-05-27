import sqlite3
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from storage import db

def extract_keywords(query: str) -> list[str]:
    """Helper to clean query and extract search terms, filtering out stop words."""
    cleaned = "".join(c if c.isalnum() or c.isspace() or c == "-" else " " for c in query.lower())
    words = cleaned.split()
    
    stopwords = {
        "what", "is", "the", "a", "of", "about", "show", "me", "recent", "who", "when", "why",
        "how", "where", "can", "you", "tell", "explain", "summarize", "list", "articles", "news",
        "post", "posts", "paper", "papers", "this", "that", "it", "they", "from", "on", "in", "at",
        "are", "was", "were", "been", "have", "has", "had", "do", "does", "did", "latest", "new"
    }
    
    return [w for w in words if w not in stopwords and len(w) > 1]


def retrieve_context(query: str) -> list[dict]:
    """Retrieves relevant database entries matching keywords and recent high-signal items."""
    keywords = extract_keywords(query)
    
    matched_items = []
    if keywords:
        # Build SQL OR constraints for each word
        where_clauses = []
        params = []
        for kw in keywords:
            where_clauses.append("(title LIKE ? OR tldr LIKE ? OR summary LIKE ?)")
            kw_wildcard = f"%{kw}%"
            params.extend([kw_wildcard, kw_wildcard, kw_wildcard])
        
        sql = f"""SELECT *, 0 AS is_bookmarked FROM items
                  WHERE {' OR '.join(where_clauses)}
                  ORDER BY published_at DESC LIMIT 25"""
        with db.conn() as con:
            rows = con.execute(sql, params).fetchall()
            matched_items = [dict(r) for r in rows]
            
    # 2. Fetch the 25 most recent Major & Notable items from the last 7 days
    sql_recent = """SELECT *, 0 AS is_bookmarked FROM items
                    WHERE importance >= 2
                    AND datetime(published_at) >= datetime('now', '-7 days')
                    ORDER BY published_at DESC LIMIT 25"""
    with db.conn() as con:
        rows_recent = con.execute(sql_recent).fetchall()
        recent_items = [dict(r) for r in rows_recent]
        
    # Combine & deduplicate by URL
    combined = []
    seen_urls = set()
    for item in matched_items + recent_items:
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            combined.append(item)
            
    return combined[:40]


def answer_question(query: str, chat_history: list[dict], cfg: dict) -> str:
    """Uses keyword retrieval + recent items context to answer questions using active LLM."""
    context_items = retrieve_context(query)
    
    # Format context items
    context_blocks = []
    for idx, it in enumerate(context_items, 1):
        context_blocks.append(
            f"[{idx}] Title: {it['title']}\n"
            f"Source: {it['source']} | URL: {it['url']} | Published: {it['published_at'][:10]}\n"
            f"TL;DR: {it.get('tldr') or ''}\n"
            f"Summary: {(it.get('summary') or '')[:200]}\n"
        )
        
    context_text = "\n---\n".join(context_blocks) if context_blocks else "No relevant articles found."
    
    # System Instruction
    system_prompt = (
        "You are 'The AI Dispatch' Assistant, a helpful AI news research assistant.\n"
        "Your task is to answer the user's question about recent AI news based ONLY on the context articles provided below.\n\n"
        "Guidelines:\n"
        "1. Cite specific articles using markdown links exactly matching their URL: [Title](URL).\n"
        "2. Keep your answer factual, concise, and structured (use bullet points where appropriate).\n"
        "3. Do not invent facts. If the provided context does not contain relevant information to answer the question, "
        "politely state that you do not have information about that topic in the current feed.\n\n"
        "CONTEXT ARTICLES:\n"
        f"{context_text}"
    )
    
    # User message & History wrapper
    user_prompt_lines = []
    if chat_history:
        user_prompt_lines.append("Chat history:")
        for msg in chat_history[-6:]:  # include up to last 6 messages
            role = "User" if msg["role"] == "user" else "Assistant"
            user_prompt_lines.append(f"{role}: {msg['content']}")
        user_prompt_lines.append("")
        
    user_prompt_lines.append(f"Question: {query}")
    user_prompt = "\n".join(user_prompt_lines)
    
    # Call active LLM provider
    import classifier
    clf = classifier.get_classifier(cfg)
    return clf.generate_response(system_prompt, user_prompt)
