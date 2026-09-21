import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.feedback import record_product_feedback


class FeedbackTests(unittest.TestCase):
    def test_feedback_contains_no_user_identifier(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "feedback.db"
            record_product_feedback(str(database), 42, True)
            with sqlite3.connect(database) as conn:
                columns = [
                    row[1] for row in conn.execute("PRAGMA table_info(product_feedback)")
                ]
                row = conn.execute(
                    "SELECT product_id, helpful FROM product_feedback"
                ).fetchone()
            self.assertEqual(row, (42, 1))
            self.assertNotIn("user_id", columns)
            self.assertNotIn("query", columns)


if __name__ == "__main__":
    unittest.main()
