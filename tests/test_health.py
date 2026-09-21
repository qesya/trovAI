import tempfile
import unittest
from pathlib import Path

from awin_db import build_database
from src.health import check_database


class HealthTests(unittest.TestCase):
    def test_compatible_catalog_is_healthy(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "catalog.db"
            build_database(str(database))
            result = check_database(database)
        self.assertTrue(result["database_exists"])
        self.assertTrue(result["database_integrity"])
        self.assertTrue(result["schema_compatible"])
        self.assertEqual(result["active_products"], 20)

    def test_missing_database_is_reported_without_exception(self):
        result = check_database(Path("/tmp/does-not-exist-trovai.db"))
        self.assertFalse(result["database_exists"])
        self.assertFalse(result["database_integrity"])


if __name__ == "__main__":
    unittest.main()
