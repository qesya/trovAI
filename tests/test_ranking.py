import unittest

from src.ranking import rank_products, split_values


PRODUCTS = [
    {
        "title": "Felpa Essentials",
        "description": "Felpa sportiva con cappuccio",
        "brand": "Nike",
        "product_type": "Abbigliamento",
        "sottocategoria": "Felpe",
        "color": "Bianco e Nero",
        "material": "Cotone e Poliestere",
        "gender": "Unisex",
        "size": "S, M, L",
        "merchant": "Nike Store",
        "price": 80,
        "sale_price": 60,
    },
    {
        "title": "Pantaloni casual",
        "description": "Pantaloni per il tempo libero",
        "brand": "Example",
        "product_type": "Abbigliamento",
        "sottocategoria": "Pantaloni",
        "color": "Nero",
        "material": "Cotone",
        "gender": "Uomo",
        "size": "M",
        "merchant": "Example Store",
        "price": 50,
        "sale_price": None,
    },
]


class RankingTests(unittest.TestCase):
    def test_comma_separated_values_remain_distinct(self):
        self.assertEqual(split_values("bianco, nero"), ["bianco", "nero"])

    def test_more_relevant_product_is_ranked_first(self):
        filters = {
            "brand": "Nike",
            "sottocategoria": "Felpe",
            "color": "bianco, nero",
            "color_logic": "AND",
            "size": "M",
        }
        ranked = rank_products(PRODUCTS, filters)
        self.assertEqual(ranked[0].position, 0)
        self.assertGreater(ranked[0].score, ranked[1].score)
        self.assertIn("marca Nike", ranked[0].reasons)

    def test_ranking_is_stable_when_scores_are_equal(self):
        ranked = rank_products(PRODUCTS, {})
        self.assertEqual([item.position for item in ranked], [0, 1])


if __name__ == "__main__":
    unittest.main()
