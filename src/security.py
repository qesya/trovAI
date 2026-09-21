"""Controlli applicativi di base per input, frequenza e minimizzazione dati."""

from __future__ import annotations

import json
import re
from typing import Iterable, List, Mapping, Tuple


class InputValidationError(ValueError):
    pass


HISTORY_ALLOWED_KEYS = {
    "age_group",
    "brand",
    "color",
    "color_logic",
    "condizione",
    "excluded_color",
    "excluded_material",
    "excluded_product_type",
    "gender",
    "in_stock_only",
    "material",
    "material_logic",
    "max_price",
    "merchant",
    "min_price",
    "only_on_sale",
    "product_type",
    "size",
    "sottocategoria",
    "sort_by",
}


def sanitize_query(value: str, max_length: int = 500) -> str:
    """Rimuove caratteri di controllo e limita la dimensione inviata al modello."""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value)).strip()
    if not cleaned:
        raise InputValidationError("Inserisci una richiesta non vuota.")
    if len(cleaned) > max_length:
        raise InputValidationError(
            f"La richiesta è troppo lunga. Usa al massimo {max_length} caratteri."
        )
    return cleaned


def check_rate_limit(
    timestamps: Iterable[float],
    now: float,
    *,
    max_requests: int = 8,
    window_seconds: int = 60,
) -> Tuple[bool, List[float]]:
    recent = [
        float(timestamp)
        for timestamp in timestamps
        if now - float(timestamp) < window_seconds
    ]
    if len(recent) >= max_requests:
        return False, recent
    recent.append(float(now))
    return True, recent


def append_filter_history(
    existing: str, filters: Mapping[str, object], max_chars: int = 1000
) -> str:
    """Conserva solo campi strutturati, escludendo testo e keyword libere."""
    minimized = {
        key: value
        for key, value in filters.items()
        if key in HISTORY_ALLOWED_KEYS and value is not None
    }
    sub_queries = filters.get("sub_queries")
    if isinstance(sub_queries, list):
        minimized_sub_queries = []
        for sub_query in sub_queries:
            if isinstance(sub_query, Mapping):
                minimized_sub_queries.append(
                    {
                        key: value
                        for key, value in sub_query.items()
                        if key in HISTORY_ALLOWED_KEYS and value is not None
                    }
                )
        if minimized_sub_queries:
            minimized["sub_queries"] = minimized_sub_queries
    serialized = json.dumps(minimized, ensure_ascii=False, sort_keys=True)
    updated = f"{existing}\nFiltri precedenti: {serialized}".strip()
    return updated[-max_chars:]
