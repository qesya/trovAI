"""Catalogo normalizzato: prodotto principale, variante e offerta del merchant."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Iterable

from trovai_pipeline.feed_cleaner import CleanProduct
from trovai_pipeline.schema import ensure_prodotti_table


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _family_title(product: CleanProduct) -> str:
    """Chiave prudente: non unisce merchant diversi senza un EAN verificato."""
    title = product.clean_title
    for word in ("nero", "bianco", "blu", "rosso", "verde", "grigio", "beige", "rosa", "marrone", "giallo", "viola"):
        title = re.sub(rf"\b{word}\b", " ", title)
    title = re.sub(r"\b(?:xxs|xs|s|m|l|xl|xxl|xxxl|[3-5]\d)\b", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def ensure_normalized_schema(conn) -> None:
    # Le migrazioni qui sotto leggono `prodotti`: deve esistere.
    ensure_prodotti_table(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS catalog_products (
            id BIGSERIAL PRIMARY KEY,
            product_key TEXT NOT NULL UNIQUE,
            brand TEXT,
            canonical_title TEXT NOT NULL,
            source_title TEXT,
            clean_title TEXT NOT NULL,
            description TEXT,
            product_type TEXT,
            sottocategoria TEXT,
            gender TEXT,
            age_group TEXT,
            model_code TEXT,
            model_title TEXT,
            model_match_confidence TEXT,
            match_method TEXT NOT NULL DEFAULT 'merchant_title',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("ALTER TABLE catalog_products ADD COLUMN IF NOT EXISTS description TEXT")
    conn.execute("ALTER TABLE catalog_products ADD COLUMN IF NOT EXISTS source_title TEXT")
    conn.execute("ALTER TABLE catalog_products ADD COLUMN IF NOT EXISTS model_code TEXT")
    conn.execute("ALTER TABLE catalog_products ADD COLUMN IF NOT EXISTS model_title TEXT")
    conn.execute("ALTER TABLE catalog_products ADD COLUMN IF NOT EXISTS model_match_confidence TEXT")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_color_variants (
            id BIGSERIAL PRIMARY KEY,
            product_id BIGINT NOT NULL REFERENCES catalog_products(id) ON DELETE CASCADE,
            color_variant_key TEXT NOT NULL UNIQUE,
            color_label TEXT,
            colorway_title TEXT NOT NULL,
            model_code TEXT,
            image_link TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_variants (
            id BIGSERIAL PRIMARY KEY,
            product_id BIGINT NOT NULL REFERENCES catalog_products(id) ON DELETE CASCADE,
            color_variant_id BIGINT REFERENCES product_color_variants(id) ON DELETE SET NULL,
            variant_key TEXT NOT NULL UNIQUE,
            ean TEXT,
            size TEXT,
            color TEXT,
            material TEXT,
            quantity_label TEXT,
            enrichment_quality TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("ALTER TABLE product_variants ADD COLUMN IF NOT EXISTS color_variant_id BIGINT REFERENCES product_color_variants(id) ON DELETE SET NULL")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS product_variants_ean_unique ON product_variants(ean) WHERE ean IS NOT NULL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS merchant_offers (
            id BIGSERIAL PRIMARY KEY,
            variant_id BIGINT NOT NULL REFERENCES product_variants(id) ON DELETE CASCADE,
            advertiser_id INTEGER NOT NULL,
            advertiser_name TEXT NOT NULL,
            source_product_id TEXT NOT NULL,
            merchant_deep_link TEXT,
            aw_deep_link TEXT,
            image_link TEXT,
            price NUMERIC(12,2) NOT NULL,
            sale_price NUMERIC(12,2),
            currency TEXT NOT NULL,
            availability BOOLEAN NOT NULL DEFAULT TRUE,
            semantic_hash TEXT NOT NULL,
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(advertiser_id, source_product_id)
        )
    """)
    conn.execute("ALTER TABLE merchant_offers ADD COLUMN IF NOT EXISTS last_seen_run TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS merchant_offers_variant_idx ON merchant_offers(variant_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS merchant_offers_active_idx ON merchant_offers(availability, price)")
    conn.execute("CREATE INDEX IF NOT EXISTS product_color_variants_product_idx ON product_color_variants(product_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS product_variants_color_variant_idx ON product_variants(color_variant_id)")
    # Porta in modo non distruttivo i dati già importati al nuovo livello colore.
    conn.execute("""
        INSERT INTO product_color_variants (
            product_id, color_variant_key, color_label, colorway_title, updated_at
        )
        SELECT DISTINCT
            variants.product_id,
            md5(variants.product_id::text || '|' || COALESCE(LOWER(variants.color), 'non_specificato') || '|' || products.canonical_title),
            variants.color,
            products.canonical_title,
            CURRENT_TIMESTAMP
        FROM product_variants AS variants
        JOIN catalog_products AS products ON products.id = variants.product_id
        ON CONFLICT(color_variant_key) DO NOTHING
    """)
    conn.execute("""
        UPDATE product_variants AS variants
        SET color_variant_id = color_variants.id
        FROM product_color_variants AS color_variants
        WHERE color_variants.product_id = variants.product_id
          AND color_variants.color_variant_key = md5(
              variants.product_id::text || '|' || COALESCE(LOWER(variants.color), 'non_specificato') || '|' ||
              (SELECT canonical_title FROM catalog_products WHERE id = variants.product_id)
          )
          AND variants.color_variant_id IS NULL
    """)
    # PostgreSQL non consente a CREATE OR REPLACE di rinominare/riposizionare
    # colonne di una vista esistente. La vista non contiene dati: ricrearla evita
    # il blocco durante gli aggiornamenti della struttura del catalogo.
    conn.execute("DROP VIEW IF EXISTS catalog_search")
    conn.execute("""
        CREATE VIEW catalog_search AS
        SELECT
            offers.id,
            products.id AS product_id,
            color_variants.id AS color_variant_id,
            color_variants.colorway_title,
            variants.id AS variant_id,
            variants.variant_key AS sku,
            products.canonical_title AS title,
            products.description,
            products.brand,
            products.product_type,
            products.sottocategoria,
            products.gender,
            products.age_group,
            variants.color,
            variants.size,
            variants.material,
            offers.price,
            offers.sale_price,
            CASE WHEN offers.availability THEN 1 ELSE 0 END AS availability,
            'nuovo' AS condizione,
            offers.advertiser_name AS merchant,
            offers.image_link,
            offers.merchant_deep_link,
            offers.advertiser_id,
            offers.source_product_id AS merchant_product_id,
            offers.aw_deep_link,
            offers.currency,
            'awin' AS source,
            offers.last_seen_at AS source_updated_at
        FROM merchant_offers AS offers
        JOIN product_variants AS variants ON variants.id = offers.variant_id
        LEFT JOIN product_color_variants AS color_variants ON color_variants.id = variants.color_variant_id
        JOIN catalog_products AS products ON products.id = variants.product_id
    """)
    # Migrazione innocua dei primi dati gia importati prima dell'aggiunta della descrizione.
    conn.execute("""
        UPDATE catalog_products AS products
        SET description = legacy.description
        FROM product_variants AS variants
        JOIN merchant_offers AS offers ON offers.variant_id = variants.id
        JOIN prodotti AS legacy
          ON legacy.advertiser_id = offers.advertiser_id
         AND legacy.source_product_id = offers.source_product_id
        WHERE products.id = variants.product_id
          AND products.description IS NULL
          AND legacy.description IS NOT NULL
    """)


def clear_normalized_catalog(conn) -> None:
    """Usare solo per ricreare deliberatamente il catalogo di test."""
    conn.execute("DELETE FROM merchant_offers")
    conn.execute("DELETE FROM product_variants")
    conn.execute("DELETE FROM product_color_variants")
    conn.execute("DELETE FROM catalog_products")


def _upsert_product(conn, product: CleanProduct) -> int:
    # EAN e MPN sono identificatori verificabili: permettono di unire offerte
    # tra merchant senza affidarsi a descrizioni solo "simili".
    if product.ean:
        existing = conn.execute(
            "SELECT product_id FROM product_variants WHERE ean = ?", (product.ean,)
        ).fetchone()
        if existing:
            return existing[0]
    if product.extracted_model:
        existing = conn.execute(
            "SELECT id FROM catalog_products WHERE model_code = ? AND COALESCE(brand, '') = COALESCE(?, '')",
            (product.extracted_model, product.brand),
        ).fetchone()
        if existing:
            return existing[0]
    if product.model_title and product.model_match_confidence == "high":
        existing = conn.execute(
            "SELECT id FROM catalog_products WHERE model_title = ? AND COALESCE(brand, '') = COALESCE(?, '') AND model_match_confidence = 'high'",
            (product.model_title, product.brand),
        ).fetchone()
        if existing:
            return existing[0]

    family = _family_title(product)
    product_key = _digest(
        f"mpn:{product.brand or ''}|{product.extracted_model}"
        if product.extracted_model
        else f"gemini-model:{product.brand or ''}|{product.model_title}"
        if product.model_title and product.model_match_confidence == "high"
        else f"merchant:{product.advertiser_id}|{product.brand or ''}|{family}"
    )
    # Il padre rappresenta soltanto il modello: colori e taglie appartengono
    # ai livelli figli. La marca viene aggiunta qui solo se il feed/Gemini
    # l'ha identificata con evidenza, mai come semplice nome del negozio.
    model_name = (
        product.model_title
        if product.model_match_confidence == "high" and product.model_title
        else product.title
    )
    canonical_title = f"{model_name} {product.brand}".strip() if product.brand else model_name
    row = conn.execute("""
        INSERT INTO catalog_products (
            product_key, brand, canonical_title, source_title, clean_title, description, product_type,
            sottocategoria, gender, age_group, model_code, model_title,
            model_match_confidence, match_method, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'merchant_title', ?)
        ON CONFLICT(product_key) DO UPDATE SET
            brand=excluded.brand, canonical_title=excluded.canonical_title,
            source_title=excluded.source_title,
            clean_title=excluded.clean_title, description=excluded.description,
            product_type=excluded.product_type,
            sottocategoria=excluded.sottocategoria, gender=excluded.gender,
            age_group=excluded.age_group, model_code=excluded.model_code,
            model_title=excluded.model_title,
            model_match_confidence=excluded.model_match_confidence,
            updated_at=excluded.updated_at
        RETURNING id
    """, (
        product_key, product.brand, canonical_title, product.source_title, product.clean_title, product.description,
        product.product_type, product.sottocategoria, product.gender,
        product.age_group, product.extracted_model, product.model_title,
        product.model_match_confidence, datetime.now(timezone.utc),
    )).fetchone()
    return row[0]


def _upsert_color_variant(conn, product_id: int, product: CleanProduct) -> int:
    """Livello 2: una colorazione/modello commerciale sotto il prodotto padre."""
    color_key = (product.color or "non_specificato").strip().lower()
    model_title = product.model_title if product.model_match_confidence == "high" and product.model_title else product.title
    colorway_title = f"{model_title} {product.colorway_name}".strip() if product.colorway_name else model_title
    color_variant_key = _digest(
        f"product:{product_id}|color:{color_key}|mpn:{product.extracted_model or ''}|colorway:{product.colorway_name or ''}"
    )
    row = conn.execute("""
        INSERT INTO product_color_variants (
            product_id, color_variant_key, color_label, colorway_title,
            model_code, image_link, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(color_variant_key) DO UPDATE SET
            color_label=excluded.color_label, colorway_title=excluded.colorway_title,
            model_code=excluded.model_code, image_link=excluded.image_link,
            updated_at=excluded.updated_at
        RETURNING id
    """, (
        product_id, color_variant_key, product.color, colorway_title,
        product.extracted_model, product.image_link, datetime.now(timezone.utc),
    )).fetchone()
    return row[0]


def _upsert_variant(conn, product_id: int, color_variant_id: int, product: CleanProduct) -> int:
    variant_key = f"ean:{product.ean}" if product.ean else _digest(
        f"product:{product_id}|color_variant:{color_variant_id}|size:{product.size or ''}|material:{product.material or ''}"
    )
    row = conn.execute("""
        INSERT INTO product_variants (
            product_id, color_variant_id, variant_key, ean, size, color, material,
            enrichment_quality, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(variant_key) DO UPDATE SET
            product_id=excluded.product_id, color_variant_id=excluded.color_variant_id,
            ean=excluded.ean, size=excluded.size,
            color=excluded.color, material=excluded.material,
            enrichment_quality=excluded.enrichment_quality, updated_at=excluded.updated_at
        RETURNING id
    """, (
        product_id, color_variant_id, variant_key, product.ean, product.size, product.color,
        product.material, product.data_quality, datetime.now(timezone.utc),
    )).fetchone()
    return row[0]


def upsert_normalized_catalog(conn, products: Iterable[CleanProduct], run_id: str | None = None) -> None:
    """Mantiene le offerte separate e aggiorna prezzo/disponibilita senza IA."""
    now = datetime.now(timezone.utc)
    for product in products:
        product_id = _upsert_product(conn, product)
        color_variant_id = _upsert_color_variant(conn, product_id, product)
        variant_id = _upsert_variant(conn, product_id, color_variant_id, product)
        conn.execute("""
            INSERT INTO merchant_offers (
                variant_id, advertiser_id, advertiser_name, source_product_id,
                merchant_deep_link, aw_deep_link, image_link, price, sale_price,
                currency, availability, semantic_hash, last_seen_at, last_seen_run
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, TRUE, ?, ?, ?)
            ON CONFLICT(advertiser_id, source_product_id) DO UPDATE SET
                variant_id=excluded.variant_id, advertiser_name=excluded.advertiser_name,
                merchant_deep_link=excluded.merchant_deep_link, aw_deep_link=excluded.aw_deep_link,
                image_link=excluded.image_link, price=excluded.price,
                sale_price=excluded.sale_price, currency=excluded.currency,
                availability=excluded.availability, semantic_hash=excluded.semantic_hash,
                last_seen_at=excluded.last_seen_at, last_seen_run=excluded.last_seen_run
        """, (
            variant_id, product.advertiser_id, product.advertiser_name,
            product.source_product_id, product.merchant_deep_link, product.aw_deep_link,
            product.image_link, product.price, product.sale_price, product.currency,
            product.content_hash, now, run_id,
        ))


def mark_offer_unavailable(conn, advertiser_id: int, source_product_id: str) -> None:
    conn.execute(
        "UPDATE merchant_offers SET availability = FALSE WHERE advertiser_id = ? AND source_product_id = ?",
        (advertiser_id, source_product_id),
    )


def mark_missing_offers_unavailable(conn, advertiser_id: int, run_id: str) -> None:
    conn.execute(
        "UPDATE merchant_offers SET availability = FALSE WHERE advertiser_id = ? AND (last_seen_run IS NULL OR last_seen_run <> ?)",
        (advertiser_id, run_id),
    )
