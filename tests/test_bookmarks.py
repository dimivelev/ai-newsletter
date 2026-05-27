import unittest
import tempfile
from pathlib import Path
import sqlite3
import sys

# Add root folder to sys.path so we can import storage
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import storage.db as db

class TestBookmarksDatabase(unittest.TestCase):
    def setUp(self):
        # Create a temp DB file
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_news.db"
        
        # Override db path
        self.old_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        
        # Initialize database schema
        db.init_db()
        
        # Insert a mock item for testing
        self.item_data = {
            "source": "Test Source",
            "source_type": "rss",
            "url": "http://example.com/test",
            "title": "Test Title",
            "summary": "Test Summary",
            "author": "Test Author",
            "published_at": "2026-05-27T12:00:00Z",
            "topic": "Frontier Models",
            "importance": 2,
            "importance_why": "Testing is good",
            "tldr": "A test tldr",
            "raw_json": "{}"
        }
        db.insert_item(self.item_data)
        
        # Get the ID of the inserted item
        with db.conn() as con:
            row = con.execute("SELECT id FROM items WHERE url=?", (self.item_data["url"],)).fetchone()
            self.item_id = row["id"]

    def tearDown(self):
        # Restore db path and cleanup temp dir
        db.DB_PATH = self.old_db_path
        try:
            self.temp_dir.cleanup()
        except OSError:
            pass

    def test_add_bookmark(self):
        # Verify initial state: 0 bookmarks (this will fail/error first)
        self.assertEqual(db.count_bookmarks(), 0)
        
        # Add bookmark
        db.add_bookmark(self.item_id)
        
        # Verify count is 1
        self.assertEqual(db.count_bookmarks(), 1)
        
        # Verify fetch_bookmarked_items returns our item
        bookmarked = db.fetch_bookmarked_items()
        self.assertEqual(len(bookmarked), 1)
        self.assertEqual(bookmarked[0]["id"], self.item_id)
        
    def test_remove_bookmark(self):
        # Add bookmark first
        db.add_bookmark(self.item_id)
        self.assertEqual(db.count_bookmarks(), 1)
        
        # Remove bookmark
        db.remove_bookmark(self.item_id)
        self.assertEqual(db.count_bookmarks(), 0)
        
    def test_fetch_items_includes_bookmark_status(self):
        # Check initial fetch - should not be bookmarked
        items = db.fetch_items()
        self.assertEqual(len(items), 1)
        self.assertFalse(items[0]["is_bookmarked"])
        
        # Bookmark it
        db.add_bookmark(self.item_id)
        
        # Check fetch again - should be bookmarked
        items = db.fetch_items()
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["is_bookmarked"])


class TestBookmarksAPI(unittest.TestCase):
    def setUp(self):
        # Create a temp DB file
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_news.db"
        
        # Override db path
        self.old_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        
        # Initialize database schema
        db.init_db()
        
        # Insert a mock item
        self.item_data = {
            "source": "Test Source",
            "source_type": "rss",
            "url": "http://example.com/test",
            "title": "Test Title",
            "summary": "Test Summary",
            "author": "Test Author",
            "published_at": "2026-05-27T12:00:00Z",
            "topic": "Frontier Models",
            "importance": 2,
            "importance_why": "Testing is good",
            "tldr": "A test tldr",
            "raw_json": "{}"
        }
        db.insert_item(self.item_data)
        
        # Get item id
        with db.conn() as con:
            row = con.execute("SELECT id FROM items WHERE url=?", (self.item_data["url"],)).fetchone()
            self.item_id = row["id"]

        # Import FastAPI app and TestClient
        from fastapi.testclient import TestClient
        from web.app import app
        self.client = TestClient(app)

    def tearDown(self):
        db.DB_PATH = self.old_db_path
        try:
            self.temp_dir.cleanup()
        except OSError:
            pass

    def test_post_bookmark_api(self):
        # Verify initially not bookmarked
        self.assertEqual(db.count_bookmarks(), 0)
        
        # Call API
        resp = self.client.post(f"/api/bookmarks/{self.item_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"ok": True})
        
        # Verify bookmarked
        self.assertEqual(db.count_bookmarks(), 1)

    def test_delete_bookmark_api(self):
        # Add bookmark first
        db.add_bookmark(self.item_id)
        self.assertEqual(db.count_bookmarks(), 1)
        
        # Call API to delete
        resp = self.client.delete(f"/api/bookmarks/{self.item_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"ok": True})
        
        # Verify removed
        self.assertEqual(db.count_bookmarks(), 0)

    def test_get_bookmarked_page(self):
        # Add bookmark
        db.add_bookmark(self.item_id)
        
        # Request page with topic=Bookmarked
        resp = self.client.get("/?topic=Bookmarked")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Test Title", resp.text)


if __name__ == "__main__":
    unittest.main()
