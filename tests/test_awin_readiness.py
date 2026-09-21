import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from awin_db import build_database
from src.awin_readiness import REQUIRED_PAGES, audit


class AwinReadinessTests(unittest.TestCase):
    def make_project(self, root: Path):
        (root / "pages").mkdir()
        (root / "awin_app5.py").write_text("st.title('TrovAI')", encoding="utf-8")
        for page in REQUIRED_PAGES:
            (root / "pages" / page).write_text("st.title('Page')", encoding="utf-8")
        database = root / "shop_database.db"
        build_database(str(database))
        return database

    def test_network_and_merchant_gates_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = self.make_project(root)
            environment = {
                "SITE_OWNER": "Example SRL",
                "CONTACT_EMAIL": "support@example.test",
                "PRIVACY_EMAIL": "privacy@example.test",
                "PUBLIC_SITE_URL": "https://example.test",
                "CONTENT_RIGHTS_CONFIRMED": "true",
            }
            with patch.dict(os.environ, environment, clear=True):
                result = audit(root, database)
        self.assertTrue(result["network_application_ready"])
        self.assertFalse(result["merchant_application_ready"])
        self.assertFalse(result["merchant_launch_ready"])

    def test_unsafe_claim_blocks_application_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = self.make_project(root)
            (root / "awin_app5.py").write_text(
                "st.title('Partner Ufficiale')", encoding="utf-8"
            )
            environment = {
                "SITE_OWNER": "Example SRL",
                "CONTACT_EMAIL": "support@example.test",
                "PRIVACY_EMAIL": "privacy@example.test",
                "PUBLIC_SITE_URL": "https://example.test",
                "CONTENT_RIGHTS_CONFIRMED": "true",
            }
            with patch.dict(os.environ, environment, clear=True):
                result = audit(root, database)
        self.assertTrue(result["unsafe_claims_found"])
        self.assertFalse(result["network_application_ready"])


if __name__ == "__main__":
    unittest.main()
