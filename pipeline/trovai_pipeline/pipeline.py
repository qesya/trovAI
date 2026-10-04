"""Pipeline scalabile per i feed Awin di TrovAI.

Non viene eseguito dall'app Streamlit. E' lo strumento da usare manualmente
quando si vuole costruire o ricostruire un catalogo: scarica il feed indicato
in ``AWIN_FEED_DOWNLOAD_URL``, normalizza i prodotti, usa Gemini per campi e
titoli, poi arricchisce immagini uniche con embedding e tag visivi.

Esempio di test piccolo (50 prodotti, 10 immagini):
  python future_feed_pipeline.py --apply --catalog-limit 50 --feed-ai-limit 50 --title-ai-limit 50 --image-limit 10

Per lavorare su tutti i prodotti disponibili si usa ``--catalog-limit 0`` e,
consapevolmente, limiti IA adeguati. Il programma non invia mai chiavi o feed
nel terminale e non sovrascrive materiale/prezzo/link dichiarati dal merchant.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from google import genai

from trovai_pipeline.config import load_secrets, project_root
from trovai_pipeline.visual_sample import (
    REVIEW_MODEL,
    is_color_conflict,
    normalize_color,
    review_color,
)
from trovai_pipeline.image_embeddings import (
    DIMENSIONS,
    MODEL_NAME as EMBEDDING_MODEL,
    create_embedding,
    download_image,
)
from trovai_pipeline.visual_tags import MODEL_NAME as VISION_MODEL, VisualTags, analyze_image
from trovai_pipeline.title_review import run_review
from trovai_pipeline.database import connect_database, database_settings
from trovai_pipeline.gemini import FREE_TIER_INTERVAL_SECONDS, RateLimiter, call_with_retry
from trovai_pipeline.awin_sync import (
    bootstrap_clean_catalog,
    refresh_display_titles,
)


VISION_REQUEST_INTERVAL_SECONDS = FREE_TIER_INTERVAL_SECONDS  # 15 richieste/minuto nel Free Tier.


def ensure_future_visual_schema(conn) -> None:
    """Asset unici + collegamento per offerta: evita IA duplicata per foto uguali."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS catalog_image_ai_assets (
            id BIGSERIAL PRIMARY KEY,
            image_sha256 TEXT NOT NULL UNIQUE,
            image_link TEXT NOT NULL,
            embedding_model TEXT,
            embedding_dimensions INTEGER,
            embedding_json JSONB,
            vision_model TEXT,
            visual_primary_color TEXT,
            visual_material TEXT,
            visual_material_confidence TEXT,
            visual_confidence INTEGER,
            visual_tags_json JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS offer_visual_enrichments (
            offer_id BIGINT PRIMARY KEY REFERENCES merchant_offers(id) ON DELETE CASCADE,
            asset_id BIGINT NOT NULL REFERENCES catalog_image_ai_assets(id) ON DELETE CASCADE,
            source_color TEXT,
            effective_color TEXT,
            color_conflict BOOLEAN NOT NULL DEFAULT FALSE,
            color_resolution TEXT NOT NULL,
            color_review_model TEXT,
            color_review_json JSONB,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS offer_visual_enrichments_asset_idx ON offer_visual_enrichments(asset_id)")
    conn.execute("DROP VIEW IF EXISTS catalog_search_enriched")
    conn.execute("""
        CREATE VIEW catalog_search_enriched AS
        SELECT
            search.*,
            enrichments.effective_color,
            enrichments.color_conflict,
            enrichments.color_resolution,
            assets.embedding_model,
            assets.embedding_dimensions,
            assets.embedding_json,
            assets.vision_model,
            assets.visual_primary_color,
            assets.visual_material,
            assets.visual_material_confidence,
            assets.visual_confidence,
            assets.visual_tags_json
        FROM catalog_search AS search
        LEFT JOIN offer_visual_enrichments AS enrichments ON enrichments.offer_id = search.id
        LEFT JOIN catalog_image_ai_assets AS assets ON assets.id = enrichments.asset_id
    """)


def select_image_offers(conn, limit: int) -> list[tuple[Any, ...]]:
    sql = """
        SELECT offers.id, offers.image_link, legacy.color, legacy.material,
               legacy.title, offers.advertiser_name, offers.source_product_id
        FROM merchant_offers AS offers
        JOIN prodotti AS legacy
          ON legacy.advertiser_id = offers.advertiser_id
         AND legacy.source_product_id = offers.source_product_id
        WHERE offers.availability = TRUE
          AND offers.image_link IS NOT NULL
          AND BTRIM(offers.image_link) <> ''
        ORDER BY offers.id
    """
    if limit > 0:
        sql += " LIMIT ?"
        return list(conn.execute(sql, (limit,)).fetchall())
    return list(conn.execute(sql).fetchall())


def asset_by_hash(conn, image_hash: str) -> tuple[Any, ...] | None:
    return conn.execute("""
        SELECT id, embedding_json, visual_tags_json, visual_primary_color,
               visual_confidence, visual_material, visual_material_confidence
        FROM catalog_image_ai_assets
        WHERE image_sha256 = ?
    """, (image_hash,)).fetchone()


def upsert_asset(conn, *, image_hash: str, image_link: str, embedding: list[float] | None,
                 tags: VisualTags | None) -> tuple[Any, ...]:
    tag_payload = tags.model_dump() if tags else None
    row = conn.execute("""
        INSERT INTO catalog_image_ai_assets (
            image_sha256, image_link, embedding_model, embedding_dimensions,
            embedding_json, vision_model, visual_primary_color, visual_material,
            visual_material_confidence, visual_confidence, visual_tags_json, updated_at
        ) VALUES (?, ?, ?, ?, CAST(? AS JSONB), ?, ?, ?, ?, ?, CAST(? AS JSONB), ?)
        ON CONFLICT(image_sha256) DO UPDATE SET
            image_link = excluded.image_link,
            embedding_model = COALESCE(catalog_image_ai_assets.embedding_model, excluded.embedding_model),
            embedding_dimensions = COALESCE(catalog_image_ai_assets.embedding_dimensions, excluded.embedding_dimensions),
            embedding_json = COALESCE(catalog_image_ai_assets.embedding_json, excluded.embedding_json),
            vision_model = COALESCE(catalog_image_ai_assets.vision_model, excluded.vision_model),
            visual_primary_color = COALESCE(catalog_image_ai_assets.visual_primary_color, excluded.visual_primary_color),
            visual_material = COALESCE(catalog_image_ai_assets.visual_material, excluded.visual_material),
            visual_material_confidence = COALESCE(catalog_image_ai_assets.visual_material_confidence, excluded.visual_material_confidence),
            visual_confidence = COALESCE(catalog_image_ai_assets.visual_confidence, excluded.visual_confidence),
            visual_tags_json = COALESCE(catalog_image_ai_assets.visual_tags_json, excluded.visual_tags_json),
            updated_at = excluded.updated_at
        RETURNING id, embedding_json, visual_tags_json, visual_primary_color,
                  visual_confidence, visual_material, visual_material_confidence
    """, (
        image_hash, image_link,
        EMBEDDING_MODEL if embedding else None, DIMENSIONS if embedding else None,
        json.dumps(embedding) if embedding else None,
        VISION_MODEL if tags else None,
        tags.colore_principale if tags else None,
        tags.materiale_visivo if tags else None,
        tags.confidenza_materiale if tags else None,
        tags.confidenza_generale if tags else None,
        json.dumps(tag_payload, ensure_ascii=False) if tag_payload else None,
        datetime.now(timezone.utc),
    )).fetchone()
    return row


def enrich_images(*, apply: bool, limit: int) -> dict[str, int]:
    secrets = load_secrets()
    settings = database_settings(project_root(), secrets)
    if settings.backend != "postgres":
        raise RuntimeError("Configura PostgreSQL prima dell'arricchimento immagini.")
    embedding_key = str(secrets.get("GEMINI_EMBEDDING_API_KEY", "")).strip()
    vision_key = str(secrets.get("GEMINI_VISION_API_KEY", "")).strip()
    if apply and (not embedding_key or not vision_key):
        raise RuntimeError("Servono GEMINI_EMBEDDING_API_KEY e GEMINI_VISION_API_KEY nei secrets locali.")
    stats = {"offers_selected": 0, "assets_new": 0, "embeddings_new": 0, "tags_new": 0, "color_reviews": 0, "offers_linked": 0, "failed": 0}
    embedding_client = genai.Client(api_key=embedding_key) if apply else None
    vision_client = genai.Client(api_key=vision_key) if apply else None
    vision_limiter = RateLimiter(VISION_REQUEST_INTERVAL_SECONDS)

    with connect_database(settings) as conn:
        ensure_future_visual_schema(conn)
        offers = select_image_offers(conn, limit)
        stats["offers_selected"] = len(offers)
        for offer_id, image_link, source_color, material, title, merchant, source_product_id in offers:
            try:
                image_bytes, mime_type = download_image(str(image_link))
                image_hash = hashlib.sha256(image_bytes).hexdigest()
                asset = asset_by_hash(conn, image_hash)
                embedding: list[float] | None = None
                tags: VisualTags | None = None
                if asset is None or asset[1] is None:
                    if not apply:
                        stats["embeddings_new"] += 1
                        continue
                    embedding = call_with_retry(
                        lambda: create_embedding(embedding_client, image_bytes, mime_type), minimum_wait=0.7
                    )
                    stats["embeddings_new"] += 1
                if asset is None or asset[2] is None:
                    if not apply:
                        stats["tags_new"] += 1
                        continue
                    tags = call_with_retry(
                        lambda: analyze_image(vision_client, image_bytes, mime_type),
                        limiter=vision_limiter,
                    )
                    stats["tags_new"] += 1
                if not apply:
                    continue
                asset = upsert_asset(conn, image_hash=image_hash, image_link=str(image_link), embedding=embedding, tags=tags)
                if embedding or tags:
                    stats["assets_new"] += 1
                asset_id, _, tags_json, visual_primary_color, visual_confidence, _, _ = asset
                parsed_tags = (
                    tags.model_dump()
                    if tags
                    else tags_json
                    if isinstance(tags_json, dict)
                    else json.loads(tags_json)
                    if tags_json
                    else {}
                )
                effective_color = source_color
                conflict = is_color_conflict(source_color, parsed_tags)
                resolution = "feed_conservato" if source_color else "feed_non_specificato"
                review_json: dict[str, Any] | None = None
                review_model: str | None = None
                if not source_color and visual_primary_color and visual_primary_color != "sconosciuto" and (visual_confidence or 0) >= 80:
                    effective_color = visual_primary_color
                    resolution = "visione_per_campo_feed_vuoto"
                if conflict:
                    review = call_with_retry(
                        lambda: review_color(vision_client, image_bytes, mime_type, str(source_color), parsed_tags),
                        limiter=vision_limiter,
                    )
                    review_json = review.model_dump()
                    review_model = REVIEW_MODEL
                    stats["color_reviews"] += 1
                    if review.decisione == "usa_visione" and review.confidenza >= 80:
                        effective_color = review.colore_finale
                        resolution = "visione_confermata_da_revisione"
                    elif review.decisione == "mantieni_entrambi":
                        effective_color = ", ".join(sorted(normalize_color(str(source_color)) | normalize_color(review.colore_finale)))
                        resolution = "feed_e_visione_confermati"
                    elif review.decisione == "non_conclusivo":
                        resolution = "conflitto_non_conclusivo_feed_conservato"
                    else:
                        resolution = "feed_confermato_da_revisione"
                conn.execute("""
                    INSERT INTO offer_visual_enrichments (
                        offer_id, asset_id, source_color, effective_color, color_conflict,
                        color_resolution, color_review_model, color_review_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, CAST(? AS JSONB), ?)
                    ON CONFLICT(offer_id) DO UPDATE SET
                        asset_id = excluded.asset_id,
                        source_color = excluded.source_color,
                        effective_color = excluded.effective_color,
                        color_conflict = excluded.color_conflict,
                        color_resolution = excluded.color_resolution,
                        color_review_model = excluded.color_review_model,
                        color_review_json = excluded.color_review_json,
                        updated_at = excluded.updated_at
                """, (
                    offer_id, asset_id, source_color, effective_color, conflict, resolution,
                    review_model, json.dumps(review_json, ensure_ascii=False) if review_json else None,
                    datetime.now(timezone.utc),
                ))
                stats["offers_linked"] += 1
            except Exception as exc:
                stats["failed"] += 1
                print(f"ERRORE immagine offerta {offer_id} ({merchant}/{source_product_id}): {exc}")
    return stats


def print_stats(title: str, stats: dict[str, int]) -> None:
    print(f"\n{title}")
    for key, value in stats.items():
        print(f"{key}: {value}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline futura TrovAI: Awin, pulizia, Gemini, embedding e tag visivi.")
    parser.add_argument("--apply", action="store_true", help="Esegue scritture, download e chiamate IA. Senza questo flag non modifica nulla.")
    parser.add_argument("--replace-catalog", action="store_true", help="Conferma la sostituzione del catalogo Awin corrente con il nuovo campione selezionato.")
    parser.add_argument("--catalog-limit", type=int, default=1000, help="Prodotti Awin da importare; 0 significa tutti (predefinito: 1000).")
    parser.add_argument("--feed-ai-limit", type=int, default=1000, help="Prodotti da revisionare nel feed da Gemini (predefinito: 1000).")
    parser.add_argument("--title-ai-limit", type=int, default=1000, help="Titoli utente da formulare con Gemini (predefinito: 1000).")
    parser.add_argument("--image-limit", type=int, default=10, help="Offerte con immagine da arricchire; 0 significa tutte (predefinito: 10).")
    parser.add_argument("--skip-visual", action="store_true", help="Salta embedding, tag visivi e revisione colore.")
    args = parser.parse_args()
    if min(args.catalog_limit, args.feed_ai_limit, args.title_ai_limit, args.image_limit) < 0:
        raise SystemExit("I limiti non possono essere negativi.")
    if not args.apply:
        print("ANTEPRIMA: nessun feed verra scaricato e nessun dato verra modificato. Usa --apply per eseguire la pipeline.")
        print("Per un test reale controllato usa ad esempio: --apply --catalog-limit 50 --feed-ai-limit 50 --title-ai-limit 50 --image-limit 10")
        return
    if not args.replace_catalog:
        raise SystemExit("Operazione protetta: aggiungi --replace-catalog solo se vuoi sostituire il catalogo Awin corrente.")

    catalog_limit = args.catalog_limit or 10_000_000
    print("PIPELINE FUTURA TROVAI")
    catalog_stats = bootstrap_clean_catalog(
        limit=catalog_limit,
        ai_limit=args.feed_ai_limit,
        export_csv=project_root() / "catalogo_curato.csv",
        replace_catalog=True,
    )
    print_stats("1/4 FEED AWIN, PULIZIA E ALBERO POSTGRESQL", dict(catalog_stats))
    print(f"\n2/4 PRE-PULIZIA TITOLI\nupdated: {refresh_display_titles()}")
    title_stats = run_review(apply=True, limit=args.title_ai_limit or catalog_limit)
    print_stats("3/4 TITOLI UTENTE FORMULATI DA GEMINI", title_stats)
    if not args.skip_visual:
        visual_stats = enrich_images(apply=True, limit=args.image_limit)
        print_stats("4/4 EMBEDDING GEMINI E TAG VISIVI", visual_stats)
    print("\nPIPELINE COMPLETATA")


if __name__ == "__main__":
    main()
