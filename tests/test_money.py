import unittest

from src.money import format_price


class MoneyTests(unittest.TestCase):
    def test_known_currency_uses_symbol(self):
        self.assertEqual(format_price(12.5, "EUR"), "€12.50")

    def test_unknown_currency_uses_iso_code(self):
        self.assertEqual(format_price(12.5, "CHF"), "12.50 CHF")


if __name__ == "__main__":
    unittest.main()
