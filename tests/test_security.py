import unittest

from src.security import (
    InputValidationError,
    append_filter_history,
    check_rate_limit,
    sanitize_query,
)


class SecurityTests(unittest.TestCase):
    def test_query_control_characters_are_removed(self):
        self.assertEqual(sanitize_query("  felpa\x00 Nike  "), "felpa Nike")

    def test_long_query_is_rejected(self):
        with self.assertRaises(InputValidationError):
            sanitize_query("x" * 501)

    def test_rate_limit_rejects_ninth_request_in_window(self):
        allowed, timestamps = check_rate_limit([99.0] * 8, 100.0)
        self.assertFalse(allowed)
        self.assertEqual(len(timestamps), 8)

    def test_rate_limit_discards_old_requests(self):
        allowed, timestamps = check_rate_limit([1.0] * 8, 100.0)
        self.assertTrue(allowed)
        self.assertEqual(timestamps, [100.0])

    def test_history_excludes_free_text_fields(self):
        history = append_filter_history(
            "",
            {
                "brand": "Nike",
                "search_keywords": "regalo segreto per Mario",
                "unwanted_features": "testo libero",
            },
        )
        self.assertIn("Nike", history)
        self.assertNotIn("Mario", history)
        self.assertNotIn("testo libero", history)


if __name__ == "__main__":
    unittest.main()
