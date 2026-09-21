import gzip
import sqlite3
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from awin_db import build_database
from src.awin_feed import (
    AwinFeedError,
    FeedReference,
    download_bytes,
    import_feed_rows,
    normalize_product,
    parse_csv_bytes,
)


SAMPLE_ROW = {
    "merchant_product_id": "ABC-1",
    "product_name": "Scarpa test",
    "description": "Prodotto dimostrativo del feed",
    "brand_name": "Example",
    "product_type": "Scarpe",
    "merchant_product_category_path": "Scarpe > Sneakers",
    "search_price": "79.99",
    "rrp_price": "99.99",
    "in_stock": "true",
    "merchant_name": "Example Shop",
    "aw_deep_link": "https://www.awin1.com/example",
    "currency": "EUR",
}


class AwinFeedTests(unittest.TestCase):
    def test_download_error_does_not_expose_url_or_key(self):
        secret_url = "https://example.test/apikey/super-secret-value"
        with patch(
            "src.awin_feed.urllib.request.urlopen",
            side_effect=urllib.error.URLError("network down"),
        ):
            with self.assertRaises(AwinFeedError) as context:
                download_bytes(secret_url)
        self.assertNotIn("super-secret-value", str(context.exception))
        self.assertNotIn(secret_url, str(context.exception))

    def test_gzip_csv_is_detected(self):
        payload = gzip.compress(b"product_name,merchant_product_id\nTest,1\n")
        rows = parse_csv_bytes(payload)
        self.assertEqual(rows[0]["merchant_product_id"], "1")

    def test_normalization_preserves_current_and_old_price(self):
        product = normalize_product(SAMPLE_ROW, 123, "Example Shop")
        self.assertIsNotNone(product)
        self.assertEqual(product["sku"], "123:ABC-1")
        self.assertEqual(product["price"], 99.99)
        self.assertEqual(product["sale_price"], 79.99)
        self.assertEqual(product["aw_deep_link"], "https://www.awin1.com/example")

    def test_import_is_an_upsert_and_marks_missing_items_unavailable(self):
        reference = FeedReference(
            advertiser_id=123,
            advertiser_name="Example Shop",
            feed_id="feed-1",
            feed_name="Default",
            membership_status="Joined",
            last_imported="2026-08-19 12:00:00",
            url="https://example.test/feed.csv",
        )
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "catalog.db"
            build_database(str(database))
            with sqlite3.connect(database) as conn:
                self.assertEqual(import_feed_rows(conn, [SAMPLE_ROW], reference), 1)
                updated = dict(SAMPLE_ROW, search_price="69.99")
                self.assertEqual(import_feed_rows(conn, [updated], reference), 1)
                count = conn.execute(
                    "SELECT COUNT(*) FROM prodotti WHERE advertiser_id = 123"
                ).fetchone()[0]
                current = conn.execute(
                    "SELECT sale_price FROM prodotti WHERE advertiser_id = 123"
                ).fetchone()[0]
                self.assertEqual(count, 1)
                self.assertEqual(current, 69.99)

                second = dict(SAMPLE_ROW, merchant_product_id="ABC-2")
                import_feed_rows(conn, [second], reference)
                old_availability = conn.execute(
                    "SELECT availability FROM prodotti "
                    "WHERE advertiser_id = 123 AND merchant_product_id = 'ABC-1'"
                ).fetchone()[0]
                self.assertEqual(old_availability, 0)


if __name__ == "__main__":
    unittest.main()
