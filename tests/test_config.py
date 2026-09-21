import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.config import ConfigurationError, database_path, get_setting


class ConfigTests(unittest.TestCase):
    def test_environment_has_priority_over_secrets(self):
        with patch.dict(os.environ, {"EXAMPLE_SETTING": "from-env"}):
            self.assertEqual(
                get_setting("EXAMPLE_SETTING", {"EXAMPLE_SETTING": "from-secret"}),
                "from-env",
            )

    def test_required_setting_raises_clear_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigurationError):
                get_setting("MISSING_SETTING", required=True)

    def test_relative_database_path_is_resolved_from_app_directory(self):
        base_dir = Path(tempfile.gettempdir()) / "trovai"
        self.assertEqual(
            database_path(base_dir, "data/catalog.db"),
            base_dir / "data/catalog.db",
        )


if __name__ == "__main__":
    unittest.main()
