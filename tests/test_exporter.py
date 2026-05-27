import unittest
import tempfile
from pathlib import Path
import sqlite3
import sys

# Add root folder to sys.path so we can import storage and web
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import storage.db as db

class TestExporter(unittest.TestCase):
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
                "title": "GPT-5 Released",
                "summary": "OpenAI has officially launched GPT-5.",
                "published_at": "2026-05-27T10:00:00Z",
                "topic": "Frontier Models",
                "importance": 3,
                "importance_why": "New model release",
                "tldr": "OpenAI releases GPT-5.",
                "raw_json": "{}"
            },
            {
                "source": "arXiv cs.AI",
                "source_type": "arxiv",
                "url": "http://arxiv.org/abs/2605.1234",
                "title": "A New Reasoning Paper",
                "summary": "A paper about reasoning in LLMs.",
                "published_at": "2026-05-27T11:00:00Z",
                "topic": "Research Papers",
                "importance": 2,
                "importance_why": "Good reasoning paper",
                "tldr": "A paper examining LLM reasoning.",
                "raw_json": "{}"
            },
            {
                "source": "r/LocalLLaMA",
                "source_type": "reddit",
                "url": "http://reddit.com/r/localllama/123",
                "title": "Minor Guide",
                "summary": "A small guide about local models.",
                "published_at": "2026-05-27T12:00:00Z",
                "topic": "Tools & Infra",
                "importance": 1,
                "importance_why": "Local guide",
                "tldr": "Guide to run LLaMA locally.",
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

    def test_markdown_digest_generation(self):
        # We import the exporter here. It will fail because the module doesn't exist yet (RED).
        import storage.exporter as exporter
        
        md = exporter.generate_markdown_digest(since_hours=168, min_importance=2)
        self.assertIn("# The AI Dispatch", md)
        self.assertIn("GPT-5 Released", md)
        self.assertIn("A New Reasoning Paper", md)
        # Routine items (importance 1) should be excluded by default (min_importance=2)
        self.assertNotIn("Minor Guide", md)

        # Retrieve including routine
        md_all = exporter.generate_markdown_digest(since_hours=168, min_importance=1)
        self.assertIn("Minor Guide", md_all)

    def test_html_digest_generation(self):
        import storage.exporter as exporter
        
        html = exporter.generate_html_digest(since_hours=168, min_importance=2)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("GPT-5 Released", html)
        self.assertIn("A New Reasoning Paper", html)
        self.assertNotIn("Minor Guide", html)

    def test_api_export_endpoint(self):
        # Verify markdown download
        resp = self.client.get("/api/export/digest?format=markdown")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["content-type"], "text/markdown; charset=utf-8")
        self.assertIn("attachment", resp.headers["content-disposition"])
        self.assertIn("GPT-5 Released", resp.text)

        # Verify html download
        resp_html = self.client.get("/api/export/digest?format=html")
        self.assertEqual(resp_html.status_code, 200)
        self.assertEqual(resp_html.headers["content-type"], "text/html; charset=utf-8")
        self.assertIn("attachment", resp_html.headers["content-disposition"])
        self.assertIn("GPT-5 Released", resp_html.text)


if __name__ == "__main__":
    unittest.main()
