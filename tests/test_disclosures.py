import unittest

from src.disclosures import (
    AFFILIATE_DISCLOSURE,
    AI_DISCLOSURE,
    DEMO_DISCLOSURE,
    MERCHANT_DISCLOSURE,
    RANKING_DISCLOSURE,
)


class DisclosureTests(unittest.TestCase):
    def test_affiliate_relationship_is_explicit(self):
        text = AFFILIATE_DISCLOSURE.lower()
        self.assertIn("link affiliati", text)
        self.assertIn("commissione", text)
        self.assertIn("senza costi aggiuntivi", text)

    def test_ranking_policy_excludes_commission(self):
        text = RANKING_DISCLOSURE.lower()
        self.assertIn("commissione", text)
        self.assertIn("non è un fattore", text)

    def test_roles_are_not_ambiguous(self):
        self.assertIn("non è il venditore", MERCHANT_DISCLOSURE.lower())
        self.assertIn("intelligenza artificiale", AI_DISCLOSURE.lower())
        self.assertIn("dimostrativo", DEMO_DISCLOSURE.lower())
        self.assertIn("non è ancora", DEMO_DISCLOSURE.lower())


if __name__ == "__main__":
    unittest.main()
