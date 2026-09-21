import os
import unittest
from unittest.mock import patch

from src.site_config import load_site_identity


class SiteIdentityTests(unittest.TestCase):
    def test_identity_is_incomplete_without_legal_contacts(self):
        with patch.dict(os.environ, {}, clear=True):
            identity = load_site_identity({})
        self.assertEqual(identity.name, "TrovAI")
        self.assertFalse(identity.is_complete)

    def test_identity_is_complete_with_required_public_details(self):
        values = {
            "SITE_OWNER": "Example SRL",
            "CONTACT_EMAIL": "support@example.test",
            "PRIVACY_EMAIL": "privacy@example.test",
        }
        with patch.dict(os.environ, values, clear=True):
            identity = load_site_identity({})
        self.assertTrue(identity.is_complete)


if __name__ == "__main__":
    unittest.main()
