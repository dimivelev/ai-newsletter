import unittest
import tempfile
from pathlib import Path
import sqlite3
import sys

# Add root folder to sys.path so we can import storage and web
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import storage.db as db

class TestChatRAG(unittest.TestCase):
    def setUp(self):
        # Create a temp DB file
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_news.db"
        
        # Override db path
        self.old_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        
        # Initialize database schema
        db.init_db()
        
        # Insert mock items for testing
        self.items_data = [
            {
                "source": "OpenAI",
                "source_type": "rss",
                "url": "http://openai.com/gpt-5",
                "title": "GPT-5 Released",
                "summary": "OpenAI has officially launched GPT-5.",
                "published_at": "2026-05-27T10:00:00Z",
                "topic": "Frontier Models",
                "importance": 3,
                "importance_why": "New model",
                "tldr": "OpenAI releases GPT-5.",
                "raw_json": "{}"
            },
            {
                "source": "arXiv cs.AI",
                "source_type": "arxiv",
                "url": "http://arxiv.org/abs/2605.1234",
                "title": "A reasoning study",
                "summary": "This paper investigates reasoning behavior in large models.",
                "published_at": "2026-05-27T11:00:00Z",
                "topic": "Research Papers",
                "importance": 2,
                "importance_why": "Reasoning study",
                "tldr": "Paper examining LLM reasoning.",
                "raw_json": "{}"
            }
        ]
        
        for it in self.items_data:
            db.insert_item(it)

        # Get FastAPI Client
        from fastapi.testclient import TestClient
        from web.app import app
        self.client = TestClient(app)

    def tearDown(self):
        db.DB_PATH = self.old_db_path
        try:
            self.temp_dir.cleanup()
        except OSError:
            pass

    def test_extract_keywords(self):
        # We import the chat engine here. It will fail first (RED)
        import storage.chat as chat
        
        words = chat.extract_keywords("what is GPT-5 about?")
        self.assertIn("gpt-5", words)
        self.assertNotIn("what", words)
        self.assertNotIn("is", words)
        self.assertNotIn("about", words)

    def test_retrieve_context(self):
        import storage.chat as chat
        
        # Searching "reasoning"
        items = chat.retrieve_context("reasoning")
        self.assertTrue(len(items) >= 1)
        urls = {it["url"] for it in items}
        self.assertIn("http://arxiv.org/abs/2605.1234", urls)

    def test_api_chat_endpoint_mocked(self):
        import storage.chat as chat
        
        # Mock LLM call during API test
        original_answer_question = chat.answer_question
        chat.answer_question = lambda query, history, cfg: "Mocked AI Response: GPT-5 was released by OpenAI."
        
        try:
            payload = {
                "messages": [
                    {"role": "user", "content": "Tell me about GPT-5"}
                ]
            }
            resp = self.client.post("/api/chat", json=payload)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json(), {"content": "Mocked AI Response: GPT-5 was released by OpenAI."})
        finally:
            chat.answer_question = original_answer_question


if __name__ == "__main__":
    unittest.main()
