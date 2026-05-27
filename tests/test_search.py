import unittest
import tempfile
from pathlib import Path
import sqlite3
import sys

# Add root folder to sys.path so we can import storage
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import storage.db as db

class TestSearchDatabase(unittest.TestCase):
    def setUp(self):
        # Create a temp DB file
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_news.db"
        
        # Override db path
        self.old_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        
        # Initialize database schema
        db.init_db()
        
        # Insert mock items for testing search/filtering
        self.items_data = [
            {
                "source": "OpenAI Blog",
                "source_type": "rss",
                "url": "http://openai.com/gpt-5",
                "title": "GPT-5 Released with Advanced Intelligence",
                "summary": "OpenAI has officially launched its newest frontier model, GPT-5.",
                "published_at": "2026-05-27T10:00:00Z",
                "topic": "Frontier Models",
                "importance": 3,
                "importance_why": "New model",
                "tldr": "OpenAI releases GPT-5 model.",
                "raw_json": "{}"
            },
            {
                "source": "arXiv cs.AI",
                "source_type": "arxiv",
                "url": "http://arxiv.org/abs/2605.1234",
                "title": "Understanding LLM Reasoning Capabilities",
                "summary": "This paper investigates reasoning behavior in large language models.",
                "published_at": "2026-05-27T11:00:00Z",
                "topic": "Research Papers",
                "importance": 2,
                "importance_why": "Interesting paper",
                "tldr": "A paper examining LLM reasoning.",
                "raw_json": "{}"
            },
            {
                "source": "r/LocalLLaMA",
                "source_type": "reddit",
                "url": "http://reddit.com/r/localllama/123",
                "title": "How to run LLaMA 4 locally",
                "summary": "A guide on setting up LLaMA 4 LLM running on consumer hardware.",
                "published_at": "2026-05-27T12:00:00Z",
                "topic": "Tools & Infra",
                "importance": 1,
                "importance_why": "Local guide",
                "tldr": "Guide to run LLaMA 4 locally.",
                "raw_json": "{}"
            }
        ]
        
        for it in self.items_data:
            db.insert_item(it)

        # Get IDs
        with db.conn() as con:
            rows = con.execute("SELECT id, url FROM items").fetchall()
            self.ids = {r["url"]: r["id"] for r in rows}

    def tearDown(self):
        # Restore db path and cleanup temp dir
        db.DB_PATH = self.old_db_path
        try:
            self.temp_dir.cleanup()
        except OSError:
            pass

    def test_search_by_query(self):
        # Search "GPT-5" -> should return OpenAI item only
        results = db.fetch_items(q="GPT-5")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "http://openai.com/gpt-5")
        
        # Search "reasoning" -> should return arXiv item only (matches summary/tldr)
        results = db.fetch_items(q="reasoning")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "http://arxiv.org/abs/2605.1234")

        # Search "locally" -> should return reddit item only
        results = db.fetch_items(q="locally")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "http://reddit.com/r/localllama/123")

        # Search "LLM" -> should return arXiv and reddit items
        results = db.fetch_items(q="LLM")
        self.assertEqual(len(results), 2)

    def test_filter_by_sources(self):
        # Filter source_type = ['rss']
        results = db.fetch_items(sources=["rss"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "http://openai.com/gpt-5")

        # Filter source_type = ['arxiv', 'reddit']
        results = db.fetch_items(sources=["arxiv", "reddit"])
        self.assertEqual(len(results), 2)
        urls = {r["url"] for r in results}
        self.assertIn("http://arxiv.org/abs/2605.1234", urls)
        self.assertIn("http://reddit.com/r/localllama/123", urls)

    def test_search_and_filter_combined(self):
        # Search "LLM" with source = ['arxiv'] -> should return arxiv only
        results = db.fetch_items(q="LLM", sources=["arxiv"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "http://arxiv.org/abs/2605.1234")

    def test_search_bookmarked_items(self):
        # Bookmark two items
        openai_id = self.ids["http://openai.com/gpt-5"]
        arxiv_id = self.ids["http://arxiv.org/abs/2605.1234"]
        db.add_bookmark(openai_id)
        db.add_bookmark(arxiv_id)

        # Retrieve bookmarks with search "GPT-5"
        bookmarks = db.fetch_bookmarked_items(q="GPT-5")
        self.assertEqual(len(bookmarks), 1)
        self.assertEqual(bookmarks[0]["url"], "http://openai.com/gpt-5")

        # Retrieve bookmarks with source = ['arxiv']
        bookmarks = db.fetch_bookmarked_items(sources=["arxiv"])
        self.assertEqual(len(bookmarks), 1)
        self.assertEqual(bookmarks[0]["url"], "http://arxiv.org/abs/2605.1234")


class TestSearchAPI(unittest.TestCase):
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
                "source": "OpenAI Blog",
                "source_type": "rss",
                "url": "http://openai.com/gpt-5",
                "title": "GPT-5 Released with Advanced Intelligence",
                "summary": "OpenAI has officially launched its newest frontier model, GPT-5.",
                "published_at": "2026-05-27T10:00:00Z",
                "topic": "Frontier Models",
                "importance": 3,
                "importance_why": "New model",
                "tldr": "OpenAI releases GPT-5 model.",
                "raw_json": "{}"
            },
            {
                "source": "arXiv cs.AI",
                "source_type": "arxiv",
                "url": "http://arxiv.org/abs/2605.1234",
                "title": "Understanding LLM Reasoning Capabilities",
                "summary": "This paper investigates reasoning behavior in large language models.",
                "published_at": "2026-05-27T11:00:00Z",
                "topic": "Research Papers",
                "importance": 2,
                "importance_why": "Interesting paper",
                "tldr": "A paper examining LLM reasoning.",
                "raw_json": "{}"
            }
        ]
        
        for it in self.items_data:
            db.insert_item(it)

        with db.conn() as con:
            rows = con.execute("SELECT id, url FROM items").fetchall()
            self.ids = {r["url"]: r["id"] for r in rows}

        from fastapi.testclient import TestClient
        from web.app import app
        self.client = TestClient(app)

    def tearDown(self):
        db.DB_PATH = self.old_db_path
        try:
            self.temp_dir.cleanup()
        except OSError:
            pass

    def test_search_query_api(self):
        # Query "GPT-5"
        resp = self.client.get("/?q=GPT-5")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("GPT-5", resp.text)
        self.assertNotIn("Understanding LLM", resp.text)

    def test_sources_filter_api(self):
        # Filter source = arxiv
        resp = self.client.get("/?sources=arxiv")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Understanding LLM", resp.text)
        self.assertNotIn("GPT-5", resp.text)

    def test_combined_search_and_sources_api(self):
        # Search "LLM" from rss (should return empty)
        resp = self.client.get("/?q=LLM&sources=rss")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("Understanding LLM", resp.text)
        self.assertNotIn("GPT-5", resp.text)


if __name__ == "__main__":
    unittest.main()
