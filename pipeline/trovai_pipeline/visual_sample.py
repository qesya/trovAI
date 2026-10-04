"""Crea un catalogo dimostrativo con 10 prodotti, feed, embedding e tag visivi.

La tabella di prova non modifica mai ``prodotti`` né le tabelle normalizzate.
Il colore originale del feed viene conservato separatamente dal colore visivo.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

# Carica la connessione DB prima del client Google: su questo PC evita la DLL
# psycopg bloccata dalla policy di integrita Windows.
from trovai_pipeline.config import load_secrets, project_root
from trovai_pipeline.database import connect_database, database_settings
from trovai_pipeline.image_embeddings import EmbeddingTestError, download_image
from google import genai
from google.genai import types


TABLE_NAME = "catalogo_prova_visivo_10"
REVIEW_MODEL = "gemini-3.5-flash-lite"


class ColorReview(BaseModel):
    decisione: Literal["mantieni_feed", "usa_visione", "mantieni_entrambi", "non_conclusivo"]
    colore_finale: str = Field(description="Un colore italiano semplice oppure 'sconosciuto'.")
    confidenza: int = Field(ge=0, le=100)
    motivazione_breve: str = Field(description="Massimo una frase, basata solo su immagine e valori confrontati.")


REVIEW_PROMPT = """
Sei un revisore indipendente di dati prodotto per e-commerce.
Osserva l'immagine e confronta solo il colore dichiarato dal feed con i tag
visivi gia estratti. Non inventare dettagli non visibili.

Regole:
- Il colore del feed puo essere una componente secondaria, quindi non scartarlo
  se e chiaramente presente nella foto.
- Scegli 'usa_visione' solo se il colore feed e chiaramente assente e la foto
  mostra con buona evidenza un colore diverso.
- Scegli 'mantieni_entrambi' per prodotti multicolore o quando entrambi i
  colori sono visibili.
- Scegli 'non_conclusivo' se l'immagine non consente una decisione affidabile.
- Non valutare materiale, taglia, brand, prezzo, disponibilita o EAN.
""".strip()


def normalize_color(value: str | None) -> set[str]:
    """Confronto prudente dei colori senza alterare mai il valore originale."""
    if not value:
        return set()
    aliases = {
        "white": "bianco", "black": "nero", "blue": "blu", "red": "rosso",
        "green": "verde", "yellow": "giallo", "pink": "rosa", "purple": "viola",
        "orange": "arancione", "brown": "marrone", "grey": "grigio", "gray": "grigio",
        "cream": "beige", "ivory": "beige", "gold": "oro", "silver": "argento",
    }
    lowered = value.lower().replace("/", " ").replace(",", " ").replace("-", " ")
    values = {aliases.get(word, word) for word in lowered.split()}
    known = {"bianco", "nero", "blu", "rosso", "verde", "giallo", "rosa", "viola", "arancione", "marrone", "grigio", "beige", "oro", "argento", "multicolore"}
    return values & known


def parse_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    return json.loads(value)


def is_color_conflict(source_color: str | None, visual_tags: dict[str, Any]) -> bool:
    source = normalize_color(source_color)
    visual = normalize_color(str(visual_tags.get("colore_principale", "")))
    for color in visual_tags.get("colori_visibili", []) or []:
        visual |= normalize_color(str(color))
    if not source or not visual or "multicolore" in source or "multicolore" in visual:
        return False
    return source.isdisjoint(visual)


def review_color(client: genai.Client, image_bytes: bytes, mime_type: str, source_color: str, visual_tags: dict[str, Any]) -> ColorReview:
    context = {
        "colore_feed": source_color,
        "colore_principale_visione": visual_tags.get("colore_principale", "sconosciuto"),
        "colori_visibili_visione": visual_tags.get("colori_visibili", []),
    }
    response = client.models.generate_content(
        model=REVIEW_MODEL,
        contents=[
            REVIEW_PROMPT + "\n\nDati da confrontare:\n" + json.dumps(context, ensure_ascii=False),
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ColorReview,
            temperature=0,
        ),
    )
    if response.parsed is None:
        raise EmbeddingTestError("Gemini non ha restituito la revisione colore strutturata.")
    return ColorReview.model_validate(response.parsed)


def ensure_sample_schema(conn) -> None:
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id BIGSERIAL PRIMARY KEY,
            offer_id BIGINT NOT NULL UNIQUE,
            product_id BIGINT,
            color_variant_id BIGINT,
            sku TEXT, title TEXT, source_title TEXT, clean_title TEXT,
            extracted_model TEXT, description TEXT, brand TEXT,
            product_type TEXT, sottocategoria TEXT, gender TEXT, age_group TEXT,
            source_color TEXT, size TEXT, material TEXT,
            price NUMERIC(12,2), sale_price NUMERIC(12,2),
            discount_percentage DOUBLE PRECISION, availability BOOLEAN,
            condizione TEXT, merchant TEXT, image_link TEXT,
            merchant_deep_link TEXT, advertiser_id INTEGER, merchant_product_id TEXT,
            aw_deep_link TEXT, currency TEXT, source TEXT, ean TEXT,
            source_product_id TEXT, data_quality TEXT, normalized_at TEXT, last_seen_run TEXT,
            embedding_model TEXT NOT NULL, embedding_dimensions INTEGER NOT NULL,
            embedding_json JSONB NOT NULL,
            visual_tag_model TEXT NOT NULL, visual_primary_color TEXT,
            visual_material TEXT, visual_material_confidence TEXT,
            visual_confidence INTEGER, visual_style_tags JSONB NOT NULL,
            visual_pattern_tags JSONB NOT NULL, visual_detail_tags JSONB NOT NULL,
            visual_tags_json JSONB NOT NULL,
            color_conflict BOOLEAN NOT NULL DEFAULT FALSE,
            color_resolution TEXT NOT NULL,
            effective_color TEXT,
            color_review_model TEXT, color_review_json JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)


def fetch_sample_rows(conn) -> list[tuple[Any, ...]]:
    rows = conn.execute("""
        SELECT
            embeddings.offer_id, embeddings.color_variant_id,
            embeddings.model_name, embeddings.dimensions, embeddings.embedding_json,
            tags.model_name, tags.colore_principale, tags.materiale_visivo,
            tags.confidenza_materiale, tags.confidenza_generale, tags.tags_json,
            offers.image_link,
            products.id AS product_id,
            legacy.sku, legacy.title, legacy.source_title, legacy.clean_title,
            legacy.extracted_model, legacy.description, legacy.brand,
            legacy.product_type, legacy.sottocategoria, legacy.gender, legacy.age_group,
            legacy.color, legacy.size, legacy.material, legacy.price, legacy.sale_price,
            legacy.discount_percentage, legacy.availability, legacy.condizione,
            legacy.merchant, legacy.image_link, legacy.merchant_deep_link,
            legacy.advertiser_id, legacy.merchant_product_id, legacy.aw_deep_link,
            legacy.currency, legacy.source, legacy.ean, legacy.source_product_id,
            legacy.data_quality, legacy.normalized_at, legacy.last_seen_run
        FROM product_image_embeddings AS embeddings
        JOIN merchant_offers AS offers ON offers.id = embeddings.offer_id
        JOIN product_variants AS variants ON variants.id = offers.variant_id
        JOIN catalog_products AS products ON products.id = variants.product_id
        JOIN prodotti AS legacy
          ON legacy.advertiser_id = offers.advertiser_id
         AND legacy.source_product_id = offers.source_product_id
        JOIN product_visual_tags AS tags
          ON tags.offer_id = embeddings.offer_id
         AND tags.image_sha256 = embeddings.image_sha256
        ORDER BY embeddings.id
    """).fetchall()
    if len(rows) != 10:
        raise EmbeddingTestError(
            f"Servono 10 righe con embedding e tag visivi; ne sono state trovate {len(rows)}."
        )
    return rows


def build_catalog(*, apply: bool) -> dict[str, int]:
    secrets = load_secrets()
    key = str(secrets.get("GEMINI_VISION_API_KEY", "")).strip()
    if not key:
        raise EmbeddingTestError("Manca GEMINI_VISION_API_KEY in .streamlit/secrets.toml.")
    settings = database_settings(project_root(), secrets)
    if settings.backend != "postgres":
        raise EmbeddingTestError("Il catalogo dimostrativo richiede PostgreSQL.")

    stats = {"products": 0, "color_conflicts": 0, "reviewed": 0, "visual_color_used": 0}
    client = genai.Client(api_key=key) if apply else None
    with connect_database(settings) as conn:
        rows = fetch_sample_rows(conn)
        prepared: list[tuple[Any, ...]] = []
        for row in rows:
            (
                offer_id, color_variant_id, embedding_model, embedding_dimensions, embedding_json,
                visual_model, visual_primary_color, visual_material, visual_material_confidence,
                visual_confidence, visual_tags_json, offer_image_link, product_id,
                sku, title, source_title, clean_title, extracted_model, description, brand,
                product_type, sottocategoria, gender, age_group, source_color, size, material,
                price, sale_price, discount_percentage, availability, condizione, merchant,
                legacy_image_link, merchant_deep_link, advertiser_id, merchant_product_id,
                aw_deep_link, currency, source, ean, source_product_id, data_quality,
                normalized_at, last_seen_run,
            ) = row
            tags = parse_json(visual_tags_json)
            conflict = is_color_conflict(source_color, tags)
            resolution = "feed_non_specificato"
            effective_color = source_color
            review_json: dict[str, Any] | None = None
            review_model: str | None = None

            if source_color:
                resolution = "feed_conservato"
            elif visual_primary_color and visual_primary_color != "sconosciuto":
                effective_color = visual_primary_color
                resolution = "visione_per_campo_feed_vuoto"

            if conflict:
                stats["color_conflicts"] += 1
                if apply:
                    image_bytes, mime_type = download_image(str(offer_image_link))
                    review = review_color(client, image_bytes, mime_type, str(source_color), tags)
                    review_json = review.model_dump()
                    review_model = REVIEW_MODEL
                    stats["reviewed"] += 1
                    if review.decisione == "usa_visione" and review.confidenza >= 80:
                        effective_color = review.colore_finale
                        resolution = "visione_confermata_da_revisione"
                        stats["visual_color_used"] += 1
                    elif review.decisione == "mantieni_entrambi":
                        effective_color = ", ".join(sorted(normalize_color(str(source_color)) | normalize_color(review.colore_finale)))
                        resolution = "feed_e_visione_confermati"
                    elif review.decisione == "non_conclusivo":
                        resolution = "conflitto_non_conclusivo_feed_conservato"
                    else:
                        resolution = "feed_confermato_da_revisione"
                else:
                    resolution = "conflitto_da_revisionare"

            prepared.append((
                offer_id, product_id, color_variant_id,
                sku, title, source_title, clean_title, extracted_model, description, brand,
                product_type, sottocategoria, gender, age_group, source_color, size, material,
                price, sale_price, discount_percentage, bool(availability), condizione, merchant,
                legacy_image_link, merchant_deep_link, advertiser_id, merchant_product_id,
                aw_deep_link, currency, source, ean, source_product_id, data_quality,
                normalized_at, last_seen_run, embedding_model, embedding_dimensions,
                json.dumps(embedding_json), visual_model, visual_primary_color,
                visual_material, visual_material_confidence, visual_confidence,
                json.dumps(tags.get("stile", []), ensure_ascii=False),
                json.dumps(tags.get("motivo", []), ensure_ascii=False),
                json.dumps(tags.get("dettagli_visivi", []), ensure_ascii=False),
                json.dumps(tags, ensure_ascii=False), conflict, resolution, effective_color,
                review_model, json.dumps(review_json, ensure_ascii=False) if review_json else None,
                datetime.now(timezone.utc),
            ))
            stats["products"] += 1

        if apply:
            ensure_sample_schema(conn)
            # Questa e una tabella di prova dedicata, quindi viene ricreata con
            # le stesse dieci righe senza toccare il catalogo principale.
            conn.execute(f"DELETE FROM {TABLE_NAME}")
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
            field_names = [name.strip() for name in columns.split(",")]
            placeholders = ", ".join("?" for _ in field_names)
            conn.executemany(
                f"INSERT INTO {TABLE_NAME} ({columns}) VALUES ({placeholders})",
                prepared,
            )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Crea una scheda catalogo unificata per 10 prodotti di prova.")
    parser.add_argument("--apply", action="store_true", help="Crea/aggiorna la tabella catalogo_prova_visivo_10.")
    args = parser.parse_args()
    stats = build_catalog(apply=args.apply)
    print("CATALOGO VISIVO DI PROVA" if args.apply else "ANTEPRIMA CATALOGO VISIVO")
    for key in ("products", "color_conflicts", "reviewed", "visual_color_used"):
        print(f"{key}: {stats[key]}")


if __name__ == "__main__":
    main()
