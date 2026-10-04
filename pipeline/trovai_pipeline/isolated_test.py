"""Crea un test completo su un piccolo campione del feed Awin.

Aggiorna SOLO ``catalogo_prova_visivo_10``. Non inserisce, cancella o modifica
``prodotti``, ``catalog_products``, offerte, varianti, embedding e tag del
catalogo principale. E' quindi sicuro per provare nuove regole su 10 prodotti.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from datetime import datetime, timezone
from typing import Any

from trovai_pipeline.config import load_secrets, project_root
from trovai_pipeline.visual_sample import (
    REVIEW_MODEL,
    ensure_sample_schema,
    is_color_conflict,
    normalize_color,
    review_color,
)
from trovai_pipeline.image_embeddings import DIMENSIONS, MODEL_NAME as EMBEDDING_MODEL, create_embedding, download_image
from trovai_pipeline.visual_tags import MODEL_NAME as VISION_MODEL, VisualTags, analyze_image
from google import genai
from trovai_pipeline.title_review import review_batch, title_issues
from trovai_pipeline.database import connect_database, database_settings
from trovai_pipeline.gemini import FREE_TIER_INTERVAL_SECONDS, RateLimiter, call_with_retry
from trovai_pipeline.feed_cleaner import (
    _AGE_GROUP_RULES,
    _COLOR_RULES,
    _GENDER_RULES,
    _MATERIAL_RULES,
    CleanProduct,
    _known_canonical_value,
    clean_row,
    clean_title,
    enrich_with_gemini,
)
from trovai_pipeline.awin_sync import (
    download_rows,
    feed_enrichment_settings,
)


FLASH_INTERVAL_SECONDS = FREE_TIER_INTERVAL_SECONDS


def wait_or_retry(action, *, limiter: RateLimiter | None = None):
    """Rispetta il limite Free Tier di Flash-Lite e ritenta solo gli errori 429."""
    return call_with_retry(action, limiter=limiter)


def choose_balanced_sample(products: list[CleanProduct], limit: int, seed: int) -> list[CleanProduct]:
    """Campione casuale ma distribuito tra merchant e modelli diversi."""
    rng = random.Random(seed)
    by_merchant: dict[int, list[CleanProduct]] = {}
    for product in products:
        by_merchant.setdefault(product.advertiser_id, []).append(product)
    for values in by_merchant.values():
        rng.shuffle(values)
    seen_families: dict[int, set[str]] = {merchant: set() for merchant in by_merchant}
    indexes = {merchant: 0 for merchant in by_merchant}
    selected: list[CleanProduct] = []
    while len(selected) < limit:
        added = False
        for merchant in sorted(by_merchant):
            values = by_merchant[merchant]
            while indexes[merchant] < len(values):
                product = values[indexes[merchant]]
                indexes[merchant] += 1
                family = (product.clean_title or product.source_title).casefold()
                if family in seen_families[merchant]:
                    continue
                seen_families[merchant].add(family)
                selected.append(product)
                added = True
                break
            if len(selected) >= limit:
                break
        if not added:
            break
    return selected


def enrich_feed_fields(products: list[CleanProduct], key: str, model: str, limiter: RateLimiter) -> int:
    """Gemini trova attributi in titolo, descrizione e campi collocati male."""
    results = wait_or_retry(lambda: enrich_with_gemini(products, key, model), limiter=limiter)
    for product in products:
        metadata = results.get(product.content_hash)
        if metadata:
            product.apply_enrichment(metadata)
    return len(results)


def _canonical(value: Any, rules) -> str | None:
    return _known_canonical_value(value, rules)


def formulate_user_titles(products: list[CleanProduct], key: str, model: str, limiter: RateLimiter) -> int:
    """Gemini formula direttamente il titolo utente; il codice non lo riscrive."""
    rows = [
        {
            "id": index,
            "title": product.title,
            "source_title": product.source_title,
            "description": product.description,
            "brand": product.brand,
            "color": product.color,
            "material": product.material,
            "gender": product.gender,
            "age_group": product.age_group,
            "issues": [],
        }
        for index, product in enumerate(products)
    ]
    results = wait_or_retry(lambda: review_batch(genai.Client(api_key=key), rows, model), limiter=limiter)
    accepted = 0
    for index, product in enumerate(products):
        result = results.get(index)
        if not result:
            continue
        color = product.color or _canonical(result.get("suggested_color"), _COLOR_RULES)
        material = product.material or _canonical(result.get("suggested_material"), _MATERIAL_RULES)
        gender = product.gender or _canonical(result.get("suggested_gender"), _GENDER_RULES)
        age_group = product.age_group or _canonical(result.get("suggested_age_group"), _AGE_GROUP_RULES)
        proposed = re.sub(r"[\x00-\x1f\x7f]+", " ", str(result.get("visible_title") or ""))
        proposed = re.sub(r"\s+", " ", proposed).strip()
        if title_issues(proposed, brand=product.brand, color=color, material=material, gender=gender, age_group=age_group):
            continue
        product.color, product.material = color, material
        product.gender, product.age_group = gender, age_group
        product.title = proposed
        product.clean_title = clean_title(proposed)
        accepted += 1
    return accepted


def synthetic_offer_id(product: CleanProduct) -> int:
    raw = f"{product.advertiser_id}:{product.merchant_product_id}".encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:15], 16)


def run_test(*, apply: bool, limit: int, seed: int) -> dict[str, int]:
    secrets = load_secrets()
    feed_url = str(secrets.get("AWIN_FEED_DOWNLOAD_URL", "")).strip()
    if not feed_url:
        raise RuntimeError("Manca AWIN_FEED_DOWNLOAD_URL nei secrets locali.")
    feed_key, feed_model = feed_enrichment_settings(secrets)
    embedding_key = str(secrets.get("GEMINI_EMBEDDING_API_KEY", "")).strip()
    vision_key = str(secrets.get("GEMINI_VISION_API_KEY", "")).strip()
    if apply and (not feed_key or not embedding_key or not vision_key):
        raise RuntimeError("Servono chiavi Gemini per feed, embedding e visione nei secrets locali.")
    stats = {"received": 0, "eligible": 0, "selected": 0, "feed_enriched": 0, "titles_gemini": 0, "embeddings": 0, "visual_tags": 0, "color_reviews": 0, "saved": 0, "failed": 0}
    candidates: list[CleanProduct] = []
    with download_rows(feed_url) as rows:
        for raw in rows:
            stats["received"] += 1
            product = clean_row(raw)
            if not product or str(raw.get("availability", "")).strip().lower() != "in_stock" or not product.image_link:
                continue
            candidates.append(product)
    stats["eligible"] = len(candidates)
    selected = choose_balanced_sample(candidates, limit, seed)
    stats["selected"] = len(selected)
    if not apply:
        return stats

    flash_clock = RateLimiter(FLASH_INTERVAL_SECONDS)
    stats["feed_enriched"] = enrich_feed_fields(selected, feed_key, feed_model, flash_clock)
    stats["titles_gemini"] = formulate_user_titles(selected, feed_key, "gemini-3.5-flash-lite", flash_clock)
    if stats["titles_gemini"] != len(selected):
        raise RuntimeError(
            f"Gemini ha formulato {stats['titles_gemini']} titoli su {len(selected)}. "
            "La tabella di prova precedente e' stata lasciata invariata."
        )
    embedding_client = genai.Client(api_key=embedding_key)
    vision_client = genai.Client(api_key=vision_key)
    prepared: list[tuple[Any, ...]] = []
    for product in selected:
        try:
            image_bytes, mime_type = download_image(str(product.image_link))
            embedding = wait_or_retry(lambda: create_embedding(embedding_client, image_bytes, mime_type))
            stats["embeddings"] += 1
            tags: VisualTags = wait_or_retry(lambda: analyze_image(vision_client, image_bytes, mime_type), limiter=flash_clock)
            stats["visual_tags"] += 1
            tag_json = tags.model_dump()
            conflict = is_color_conflict(product.color, tag_json)
            effective_color = product.color
            resolution = "feed_conservato" if product.color else "feed_non_specificato"
            review_json: dict[str, Any] | None = None
            review_model: str | None = None
            if not product.color and tags.colore_principale != "sconosciuto" and tags.confidenza_generale >= 80:
                effective_color = tags.colore_principale
                resolution = "visione_per_campo_feed_vuoto"
            if conflict:
                review = wait_or_retry(
                    lambda: review_color(vision_client, image_bytes, mime_type, str(product.color), tag_json),
                    limiter=flash_clock,
                )
                review_json, review_model = review.model_dump(), REVIEW_MODEL
                stats["color_reviews"] += 1
                if review.decisione == "usa_visione" and review.confidenza >= 80:
                    effective_color, resolution = review.colore_finale, "visione_confermata_da_revisione"
                elif review.decisione == "mantieni_entrambi":
                    effective_color = ", ".join(sorted(normalize_color(str(product.color)) | normalize_color(review.colore_finale)))
                    resolution = "feed_e_visione_confermati"
                elif review.decisione == "non_conclusivo":
                    resolution = "conflitto_non_conclusivo_feed_conservato"
                else:
                    resolution = "feed_confermato_da_revisione"
            now = datetime.now(timezone.utc)
            prepared.append((
                synthetic_offer_id(product), None, None,
                f"test:{product.advertiser_id}:{product.merchant_product_id}", product.title, product.source_title,
                product.clean_title, product.extracted_model, product.description, product.brand,
                product.product_type, product.sottocategoria, product.gender, product.age_group,
                product.color, product.size, product.material, product.price, product.sale_price,
                product.discount_percentage, True, "nuovo", product.advertiser_name, product.image_link,
                product.merchant_deep_link, product.advertiser_id, product.merchant_product_id,
                product.aw_deep_link, product.currency, "awin_isolated_test", product.ean,
                product.source_product_id, "gemini_visual_test", now.isoformat(), f"isolated-{seed}",
                EMBEDDING_MODEL, DIMENSIONS, json.dumps(embedding), VISION_MODEL, tags.colore_principale,
                tags.materiale_visivo, tags.confidenza_materiale, tags.confidenza_generale,
                json.dumps(tag_json.get("stile", []), ensure_ascii=False),
                json.dumps(tag_json.get("motivo", []), ensure_ascii=False),
                json.dumps(tag_json.get("dettagli_visivi", []), ensure_ascii=False),
                json.dumps(tag_json, ensure_ascii=False), conflict, resolution, effective_color,
                review_model, json.dumps(review_json, ensure_ascii=False) if review_json else None, now,
            ))
        except Exception as exc:
            stats["failed"] += 1
            print(f"ERRORE prodotto test {product.advertiser_name}/{product.merchant_product_id}: {exc}")

    if len(prepared) != len(selected):
        raise RuntimeError(
            f"Elaborati {len(prepared)} prodotti su {len(selected)}. "
            "La tabella di prova precedente e' stata lasciata invariata."
        )
    settings = database_settings(project_root(), secrets)
    if settings.backend != "postgres":
        raise RuntimeError("Il test isolato richiede PostgreSQL.")
    with connect_database(settings) as conn:
        ensure_sample_schema(conn)
        # L'unica tabella cancellata e ricreata e quella di prova richiesta.
        conn.execute("DELETE FROM catalogo_prova_visivo_10")
        columns = """
            offer_id, product_id, color_variant_id, sku, title, source_title, clean_title,
            extracted_model, description, brand, product_type, sottocategoria, gender, age_group,
            source_color, size, material, price, sale_price, discount_percentage, availability,
            condizione, merchant, image_link, merchant_deep_link, advertiser_id, merchant_product_id,
            aw_deep_link, currency, source, ean, source_product_id, data_quality, normalized_at,
            last_seen_run, embedding_model, embedding_dimensions, embedding_json, visual_tag_model,
            visual_primary_color, visual_material, visual_material_confidence, visual_confidence,
            visual_style_tags, visual_pattern_tags, visual_detail_tags, visual_tags_json,
            color_conflict, color_resolution, effective_color, color_review_model,
            color_review_json, created_at
        """
        field_names = [field.strip() for field in columns.split(",")]
        placeholders = ", ".join("?" for _ in field_names)
        if prepared:
            conn.executemany(f"INSERT INTO catalogo_prova_visivo_10 ({columns}) VALUES ({placeholders})", prepared)
    stats["saved"] = len(prepared)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Test isolato: sostituisce solo catalogo_prova_visivo_10.")
    parser.add_argument("--apply", action="store_true", help="Scarica il feed, usa Gemini e sostituisce solo la tabella di prova.")
    parser.add_argument("--limit", type=int, default=10, help="Numero prodotti casuali bilanciati (predefinito: 10).")
    parser.add_argument("--seed", type=int, default=20261004, help="Seed per estrarre un campione diverso ma ripetibile.")
    args = parser.parse_args()
    if args.limit < 1:
        raise SystemExit("limit deve essere almeno 1.")
    stats = run_test(apply=args.apply, limit=args.limit, seed=args.seed)
    print("TEST ISOLATO COMPLETATO" if args.apply else "ANTEPRIMA TEST ISOLATO")
    for key, value in stats.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
