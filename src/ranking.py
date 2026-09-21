"""Ranking deterministico e spiegabile dei prodotti candidati."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, List, Mapping, Sequence


STOPWORDS = {
    "a",
    "al",
    "con",
    "da",
    "del",
    "di",
    "e",
    "in",
    "il",
    "la",
    "o",
    "per",
    "un",
    "una",
}


@dataclass(frozen=True)
class RankedProduct:
    position: int
    score: int
    reasons: Sequence[str]


def normalize(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def split_values(value: Any) -> List[str]:
    if value is None:
        return []
    parts = re.split(r",|\s+(?:e|o)\s+", str(value), flags=re.IGNORECASE)
    return [normalized for part in parts if (normalized := normalize(part))]


def _contains(haystack: Any, needle: Any) -> bool:
    normalized_needle = normalize(needle)
    return bool(normalized_needle and normalized_needle in normalize(haystack))


def _multi_match(product_value: Any, requested: Any, logic: str) -> bool:
    values = split_values(requested)
    if not values:
        return False
    matches = [_contains(product_value, value) for value in values]
    return all(matches) if str(logic).upper() == "AND" else any(matches)


def rank_products(
    products: Iterable[Mapping[str, Any]], filters: Mapping[str, Any]
) -> List[RankedProduct]:
    ranked = []
    for position, product in enumerate(products):
        score = 0
        reasons = []

        if filters.get("brand") and _contains(product.get("brand"), filters["brand"]):
            score += 30
            reasons.append(f"marca {product.get('brand')}")

        searchable_category = " ".join(
            str(product.get(field) or "")
            for field in ("product_type", "sottocategoria", "title")
        )
        if filters.get("sottocategoria") and _contains(
            searchable_category, filters["sottocategoria"]
        ):
            score += 35
            reasons.append(f"categoria {product.get('sottocategoria')}")
        elif filters.get("product_type") and _contains(
            searchable_category, filters["product_type"]
        ):
            score += 20
            reasons.append(f"tipologia {product.get('product_type')}")

        if filters.get("color") and _multi_match(
            product.get("color"), filters["color"], filters.get("color_logic", "OR")
        ):
            score += 15
            reasons.append(f"colore {product.get('color')}")

        if filters.get("material") and _multi_match(
            product.get("material"),
            filters["material"],
            filters.get("material_logic", "OR"),
        ):
            score += 10
            reasons.append(f"materiale {product.get('material')}")

        for field, points, label in (
            ("gender", 8, "genere"),
            ("size", 8, "taglia"),
            ("merchant", 8, "negozio"),
            ("condizione", 5, "condizione"),
        ):
            if filters.get(field) and _contains(product.get(field), filters[field]):
                score += points
                reasons.append(f"{label} {product.get(field)}")

        keywords = [
            word
            for word in normalize(filters.get("search_keywords")).split()
            if len(word) > 2 and word not in STOPWORDS
        ]
        searchable_text = " ".join(
            normalize(product.get(field))
            for field in ("title", "description", "product_type", "sottocategoria")
        )
        keyword_matches = sum(word in searchable_text for word in keywords)
        if keyword_matches:
            score += min(keyword_matches * 4, 20)
            reasons.append(f"{keyword_matches} parole chiave pertinenti")

        ranked.append(
            RankedProduct(
                position=position,
                score=score,
                reasons=tuple(reasons[:3]) or ("corrisponde ai filtri applicati",),
            )
        )

    return sorted(ranked, key=lambda item: (-item.score, item.position))
