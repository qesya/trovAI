"""Importa un feed Awin diretto in PostgreSQL, a batch e in locale."""

from __future__ import annotations

import argparse
import csv
import gzip
import http.client
import io
import json
import shutil
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Mapping

from trovai_pipeline.config import load_secrets, project_root
from trovai_pipeline.database import connect_database, database_settings
from trovai_pipeline.gemini import RateLimiter, call_with_retry
from trovai_pipeline.schema import ensure_prodotti_table
from trovai_pipeline.feed_cleaner import CleanProduct, clean_display_title, clean_row, clean_title, enrich_with_gemini
from trovai_pipeline.normalized_catalog import (
    clear_normalized_catalog,
    ensure_normalized_schema,
    mark_missing_offers_unavailable,
    mark_offer_unavailable,
    upsert_normalized_catalog,
)

BATCH_SIZE = 500
AI_BATCH_SIZE = 20
EXPORT_COLUMNS = (
    "advertiser_id", "advertiser_name", "source_product_id", "ean", "title", "source_title",
    "clean_title", "extracted_model", "brand", "product_type", "sottocategoria",
    "gender", "color", "size", "material", "price", "sale_price",
    "discount_percentage", "availability", "merchant_deep_link", "aw_deep_link",
    "image_link", "currency", "data_quality",
)


class FeedSyncError(RuntimeError):
    pass


def detect_encoding(sample: bytes) -> str:
    """Sceglie un encoding comune senza aggiungere dipendenze pesanti."""
    if sample.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    candidates = ("utf-8", "cp1252", "iso-8859-1")
    scored: list[tuple[int, str]] = []
    for encoding in candidates:
        try:
            decoded = sample.decode(encoding)
        except UnicodeDecodeError:
            continue
        controls = sum(1 for char in decoded if ord(char) < 32 and char not in "\n\r\t")
        # UTF-8 e' preferito quando il contenuto e' valido in piu' formati.
        scored.append((controls + (0 if encoding == "utf-8" else 1), encoding))
    if not scored:
        return "utf-8"
    return min(scored)[1]



@contextmanager
def download_rows(url: str) -> Iterator[csv.DictReader]:
    """Completa il download prima di elaborare: evita cataloghi parziali e costi IA duplicati."""
    temporary_path: Path | None = None
    try:
        for attempt in range(3):
            try:
                with tempfile.NamedTemporaryFile(prefix="trovai-awin-", suffix=".feed", delete=False) as target:
                    temporary_path = Path(target.name)
                    request = urllib.request.Request(
                        url,
                        headers={"User-Agent": "TrovAI-Local-Feed-Sync/1.0", "Accept-Encoding": "identity"},
                    )
                    with urllib.request.urlopen(request, timeout=180) as response:
                        shutil.copyfileobj(response, target, length=1024 * 1024)
                break
            except (OSError, http.client.HTTPException, urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
                if temporary_path and temporary_path.exists():
                    temporary_path.unlink()
                temporary_path = None
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
        if temporary_path is None:
            raise OSError("Download Awin non completato")
        with temporary_path.open("rb") as source:
            compressed = source.read(2) == b"\x1f\x8b"
            source.seek(0)
            stream = gzip.GzipFile(fileobj=source) if compressed else source
            encoding = detect_encoding(stream.read(512_000))
            stream.seek(0)
            with io.TextIOWrapper(stream, encoding=encoding, errors="replace", newline="") as text:
                yield csv.DictReader(text, strict=False)
    except (OSError, http.client.HTTPException, urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise FeedSyncError("Impossibile scaricare o leggere il feed Awin.") from exc
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def ensure_schema(conn) -> None:
    ensure_prodotti_table(conn)
    # L'EAN (quando presente) è l'identità commerciale del prodotto nel merchant.
    # L'ID di origine resta consultabile, ma non può essere unico: alcuni feed
    # pubblicano più righe tecniche per lo stesso EAN.
    conn.execute("DROP INDEX IF EXISTS idx_prodotti_awin_source_identity")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_prodotti_awin_source_lookup ON prodotti(advertiser_id, source_product_id) WHERE source = 'awin' AND source_product_id IS NOT NULL")
    conn.execute("CREATE TABLE IF NOT EXISTS feed_enrichment_cache (content_hash TEXT PRIMARY KEY, metadata_json TEXT NOT NULL, enriched_at TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS feed_import_runs (run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, processed_count INTEGER NOT NULL DEFAULT 0, imported_count INTEGER NOT NULL DEFAULT 0, deleted_count INTEGER NOT NULL DEFAULT 0, ai_count INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL)")


def cached_enrichments(conn, hashes: list[str]) -> dict[str, dict]:
    if not hashes:
        return {}
    placeholders = ", ".join("?" for _ in hashes)
    rows = conn.execute(f"SELECT content_hash, metadata_json FROM feed_enrichment_cache WHERE content_hash IN ({placeholders})", hashes).fetchall()
    return {row[0]: json.loads(row[1]) for row in rows}


def store_enrichments(conn, values: Mapping[str, Mapping]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany("INSERT INTO feed_enrichment_cache (content_hash, metadata_json, enriched_at) VALUES (?, ?, ?) ON CONFLICT(content_hash) DO UPDATE SET metadata_json=excluded.metadata_json, enriched_at=excluded.enriched_at", ((key, json.dumps(value, ensure_ascii=False), now) for key, value in values.items()))


def feed_enrichment_settings(secrets: Mapping[str, object]) -> tuple[str | None, str]:
    """Restituisce una chiave e un modello adatti alla revisione testuale.

    GEMINI_FEED_API_KEY e' opzionale: se manca, la stessa chiave Free Tier
    usata per i tag visivi puo' fare anche la revisione del feed. Non stampiamo
    mai il valore della chiave nei log.
    """
    api_key = next(
        (
            str(secrets.get(name, "")).strip()
            for name in ("GEMINI_FEED_API_KEY", "GEMINI_VISION_API_KEY", "GEMINI_API_KEY")
            if str(secrets.get(name, "")).strip()
        ),
        None,
    )
    model = str(secrets.get("FEED_ENRICHMENT_MODEL", "gemini-3.5-flash-lite")).strip()
    return api_key, model or "gemini-3.5-flash-lite"


@dataclass
class EnrichmentResult:
    enriched: int = 0
    failed: int = 0


def apply_enrichment(conn, products: list[CleanProduct], api_key: str | None, model: str, remaining_budget: int, *,
                     review_all: bool = False, force_fresh: bool = False,
                     limiter: RateLimiter | None = None,
                     enrich: Callable[[list[CleanProduct], str, str], dict[str, dict]] = enrich_with_gemini) -> EnrichmentResult:
    """Applica cache e Gemini. Rispetta la quota e conta i blocchi falliti.

    Prima i blocchi da 20 partivano uno dopo l'altro senza pausa e un errore
    di quota svuotava silenziosamente il risultato: ora ogni blocco attende il
    proprio turno, i 429 vengono ritentati e gli altri errori sono contati.
    """
    result = EnrichmentResult()
    candidates = products if review_all else [product for product in products if product.needs_ai]
    cache = {} if force_fresh else cached_enrichments(conn, [product.content_hash for product in candidates])
    for product in candidates:
        if product.content_hash in cache:
            product.apply_enrichment(cache[product.content_hash])
    to_enrich = (candidates if force_fresh else [product for product in candidates if product.content_hash not in cache])[:remaining_budget]
    if not to_enrich or not api_key:
        return result
    limiter = limiter or RateLimiter()
    fresh: dict[str, dict] = {}
    for start in range(0, len(to_enrich), AI_BATCH_SIZE):
        batch = to_enrich[start:start + AI_BATCH_SIZE]
        try:
            batch_result = call_with_retry(lambda: enrich(batch, api_key, model), limiter=limiter)
        except Exception as exc:
            result.failed += len(batch)
            print(f"ERRORE Gemini blocco feed {start + 1}-{start + len(batch)}: {type(exc).__name__}: {exc}")
            continue
        result.failed += sum(1 for product in batch if product.content_hash not in batch_result)
        fresh.update(batch_result)
    store_enrichments(conn, fresh)
    for product in to_enrich:
        if product.content_hash in fresh:
            product.apply_enrichment(fresh[product.content_hash])
    result.enriched = len(fresh)
    return result


def select_balanced_products(products: list[CleanProduct], limit: int) -> list[CleanProduct]:
    """Seleziona merchant e modelli diversi prima delle semplici taglie.

    Nei feed fashion una scarpa puo comparire dieci volte, una per taglia. Per
    il catalogo iniziale vogliamo esplorare molti modelli e colori, non riempire
    il campione con le varianti numeriche dello stesso articolo.
    """
    groups: dict[int, list[CleanProduct]] = defaultdict(list)
    deferred_variants: dict[int, list[CleanProduct]] = defaultdict(list)
    seen_families: dict[int, set[str]] = defaultdict(set)
    for product in products:
        # clean_title e gia privo della taglia: e un'identita sufficientemente
        # stabile per evitare di selezionare 36, 37, 38... dello stesso modello.
        family = (product.clean_title or product.title or product.source_title).casefold()
        if family in seen_families[product.advertiser_id]:
            deferred_variants[product.advertiser_id].append(product)
        else:
            seen_families[product.advertiser_id].add(family)
            groups[product.advertiser_id].append(product)

    # Solo se non ci sono abbastanza modelli distinti, usiamo le altre taglie.
    for advertiser_id, variants in deferred_variants.items():
        groups[advertiser_id].extend(variants)
    selected: list[CleanProduct] = []
    indexes = {advertiser_id: 0 for advertiser_id in groups}
    while len(selected) < limit:
        added = False
        for advertiser_id in sorted(groups):
            index = indexes[advertiser_id]
            if index >= len(groups[advertiser_id]) or len(selected) >= limit:
                continue
            selected.append(groups[advertiser_id][index])
            indexes[advertiser_id] += 1
            added = True
        if not added:
            break
    return selected


def bootstrap_clean_catalog(*, limit: int, ai_limit: int, export_csv: Path | None, replace_catalog: bool) -> Counter:
    """Crea il primo catalogo controllato, bilanciato tra tutti i merchant del feed."""
    if not replace_catalog:
        raise FeedSyncError("La modalita iniziale richiede --replace-catalog: sostituisce demo e precedenti prodotti Awin.")
    secrets = load_secrets()
    feed_url = str(secrets.get("AWIN_FEED_DOWNLOAD_URL", "")).strip()
    if not feed_url:
        raise FeedSyncError("Aggiungi AWIN_FEED_DOWNLOAD_URL nel file .env (o come variabile d'ambiente).")
    settings = database_settings(project_root(), secrets)
    if settings.backend != "postgres":
        raise FeedSyncError("Configura PostgreSQL prima di importare il feed.")
    stats, candidates = Counter(), []
    with download_rows(feed_url) as rows:
        for raw_row in rows:
            stats["received"] += 1
            product = clean_row(raw_row)
            if product is None:
                stats["skipped_invalid"] += 1
                continue
            if str(raw_row.get("availability", "")).strip().lower() != "in_stock":
                stats["removed_unavailable"] += 1
                continue
            candidates.append(product)
    selected = select_balanced_products(candidates, limit)
    stats["eligible"] = len(candidates)
    stats["selected"] = len(selected)
    if not selected:
        raise FeedSyncError("Nessun prodotto disponibile e valido nel feed.")
    export_handle = export_csv.open("w", encoding="utf-8", newline="") if export_csv else None
    writer = csv.DictWriter(export_handle, fieldnames=EXPORT_COLUMNS) if export_handle else None
    if writer:
        writer.writeheader()
    try:
        with connect_database(settings) as conn:
            ensure_schema(conn)
            ensure_normalized_schema(conn)
            bootstrap_run_id = "bootstrap-" + uuid.uuid4().hex
            conn.execute("DELETE FROM prodotti WHERE source IN ('demo', 'awin')")
            clear_normalized_catalog(conn)
            gemini_key, model = feed_enrichment_settings(secrets)
            enrichment = apply_enrichment(
                conn, selected, gemini_key, model, ai_limit,
                review_all=True, force_fresh=True,
            )
            stats["ai"] = enrichment.enriched
            stats["ai_failed"] = enrichment.failed
            upsert_products(conn, selected, bootstrap_run_id)
            upsert_normalized_catalog(conn, selected, bootstrap_run_id)
            if writer:
                export_products(writer, selected)
    finally:
        if export_handle:
            export_handle.close()
    return stats


def upsert_products(conn, products: list[CleanProduct], run_id: str) -> None:
    if not products:
        return
    now = datetime.now(timezone.utc).isoformat()
    columns = "sku, title, source_title, clean_title, extracted_model, description, brand, product_type, sottocategoria, gender, age_group, color, size, material, price, sale_price, discount_percentage, availability, condizione, merchant, image_link, merchant_deep_link, advertiser_id, merchant_product_id, aw_deep_link, currency, source, ean, source_product_id, data_quality, normalized_at, last_seen_run"
    # Evita doppioni già all'interno dello stesso blocco: l'ultima riga del feed
    # aggiorna il prodotto con il medesimo EAN/SKU.
    unique_products = {f"{p.advertiser_id}:{p.merchant_product_id}": p for p in products}
    values = [(f"{p.advertiser_id}:{p.merchant_product_id}", p.title, p.source_title, p.clean_title, p.extracted_model, p.description, p.brand, p.product_type, p.sottocategoria, p.gender, p.age_group, p.color, p.size, p.material, p.price, p.sale_price, p.discount_percentage, 1, "nuovo", p.advertiser_name, p.image_link, p.merchant_deep_link, p.advertiser_id, p.merchant_product_id, p.aw_deep_link, p.currency, "awin", p.ean, p.source_product_id, p.data_quality, now, run_id) for p in unique_products.values()]
    fields = [field.strip() for field in columns.split(",")]
    placeholders = ", ".join("?" for _ in fields)
    updates = ", ".join(f"{field}=excluded.{field}" for field in fields if field != "sku")
    conn.executemany(f"INSERT INTO prodotti ({columns}) VALUES ({placeholders}) ON CONFLICT(sku) DO UPDATE SET {updates}", values)


def export_products(writer: csv.DictWriter, products: list[CleanProduct]) -> None:
    """Produce un CSV UTF-8 pulito, senza URL alterati e senza colonne tecniche inutili."""
    for product in products:
        writer.writerow({
            "advertiser_id": product.advertiser_id, "advertiser_name": product.advertiser_name,
            "source_product_id": product.source_product_id, "ean": product.ean or "",
            "title": product.title, "source_title": product.source_title, "clean_title": product.clean_title,
            "extracted_model": product.extracted_model or "", "brand": product.brand or "",
            "product_type": product.product_type or "", "sottocategoria": product.sottocategoria or "",
            "gender": product.gender or "", "color": product.color or "", "size": product.size or "",
            "material": product.material or "", "price": f"{product.price:.2f}",
            "sale_price": f"{product.sale_price:.2f}" if product.sale_price is not None else "",
            "discount_percentage": f"{product.discount_percentage:.2f}" if product.discount_percentage is not None else "",
            "availability": "in_stock", "merchant_deep_link": product.merchant_deep_link or "",
            "aw_deep_link": product.aw_deep_link or "", "image_link": product.image_link or "",
            "currency": product.currency, "data_quality": product.data_quality,
        })


def refresh_display_titles() -> int:
    """Ripulisce i titoli già importati senza riscaricare il feed o chiamare Gemini."""
    secrets = load_secrets()
    settings = database_settings(project_root(), secrets)
    if settings.backend != "postgres":
        raise FeedSyncError("Configura PostgreSQL prima di aggiornare i titoli.")
    with connect_database(settings) as conn:
        ensure_schema(conn)
        ensure_normalized_schema(conn)
        rows = conn.execute(
            "SELECT id, title, source_title, brand, color, material, gender, age_group "
            "FROM prodotti WHERE source = 'awin'"
        ).fetchall()
        updates = []
        for row in rows:
            source_title = str(row[2] or row[1] or "").strip()
            if not source_title:
                continue
            title = clean_display_title(
                source_title,
                brand=row[3],
                color=row[4],
                material=row[5],
                gender=row[6],
                age_group=row[7],
            )
            # `clean_title` deve essere derivato dal titolo gia' ripulito e
            # non dal titolo grezzo del feed: altrimenti i residui grammaticali
            # continuano a contaminare raggruppamenti e ricerca.
            updates.append((title, clean_title(title), source_title, row[0]))
        if updates:
            conn.executemany(
                "UPDATE prodotti SET title = ?, clean_title = ?, source_title = ? WHERE id = ?", updates
            )
            # Per ogni prodotto aggregato scegliamo una delle sue offerte disponibili:
            # le varianti e i prezzi restano invece nelle tabelle dedicate.
            conn.execute("""
                UPDATE catalog_products AS products
                SET canonical_title = CASE
                        WHEN chosen.brand IS NULL OR BTRIM(chosen.brand) = '' THEN chosen.title
                        ELSE chosen.title || ' ' || chosen.brand
                    END,
                    clean_title = chosen.clean_title,
                    source_title = chosen.source_title,
                    updated_at = CURRENT_TIMESTAMP
                FROM (
                    SELECT DISTINCT ON (variants.product_id)
                        variants.product_id, legacy.title, legacy.clean_title, legacy.source_title, legacy.brand
                    FROM product_variants AS variants
                    JOIN merchant_offers AS offers ON offers.variant_id = variants.id
                    JOIN prodotti AS legacy
                      ON legacy.advertiser_id = offers.advertiser_id
                     AND legacy.source_product_id = offers.source_product_id
                    WHERE offers.availability = TRUE
                    ORDER BY variants.product_id, offers.sale_price NULLS LAST, offers.price
                ) AS chosen
                WHERE products.id = chosen.product_id
            """)
    return len(updates)


def sync(*, apply: bool, ai_limit: int, export_csv: Path | None = None) -> Counter:
    secrets = load_secrets()
    feed_url = str(secrets.get("AWIN_FEED_DOWNLOAD_URL", "")).strip()
    if not feed_url:
        raise FeedSyncError("Aggiungi AWIN_FEED_DOWNLOAD_URL nel file .env (o come variabile d'ambiente).")
    settings = database_settings(project_root(), secrets)
    if settings.backend != "postgres":
        raise FeedSyncError("Configura PostgreSQL prima di importare il feed.")
    run_id, stats = uuid.uuid4().hex, Counter()
    gemini_key, model = feed_enrichment_settings(secrets)
    limiter = RateLimiter()
    seen_advertisers: set[int] = set()
    export_handle = export_csv.open("w", encoding="utf-8", newline="") if export_csv else None
    writer = csv.DictWriter(export_handle, fieldnames=EXPORT_COLUMNS) if export_handle else None
    if writer:
        writer.writeheader()
    try:
      with connect_database(settings) as conn:
        ensure_schema(conn)
        ensure_normalized_schema(conn)
        if apply:
            conn.execute("INSERT INTO feed_import_runs (run_id, started_at, status) VALUES (?, ?, 'running')", (run_id, datetime.now(timezone.utc).isoformat()))
        with download_rows(feed_url) as rows:
            batch: list[CleanProduct] = []
            for raw_row in rows:
                stats["received"] += 1
                product = clean_row(raw_row)
                if product is None:
                    stats["skipped_invalid"] += 1
                    continue
                seen_advertisers.add(product.advertiser_id)
                if str(raw_row.get("availability", "")).strip().lower() != "in_stock":
                    stats["removed_unavailable"] += 1
                    if apply:
                        result = conn.execute("DELETE FROM prodotti WHERE source = 'awin' AND advertiser_id = ? AND source_product_id = ?", (product.advertiser_id, product.source_product_id))
                        stats["deleted"] += max(result.rowcount or 0, 0)
                        mark_offer_unavailable(conn, product.advertiser_id, product.source_product_id)
                    continue
                batch.append(product)
                if len(batch) >= BATCH_SIZE:
                    if apply:
                        enrichment = apply_enrichment(conn, batch, gemini_key, model, max(ai_limit - stats["ai"] - stats["ai_failed"], 0), limiter=limiter)
                        stats["ai"] += enrichment.enriched
                        stats["ai_failed"] += enrichment.failed
                    if writer:
                        export_products(writer, batch)
                    if apply:
                        upsert_products(conn, batch, run_id)
                        upsert_normalized_catalog(conn, batch, run_id)
                    stats["eligible"] += len(batch)
                    batch = []
            if batch:
                if apply:
                    enrichment = apply_enrichment(conn, batch, gemini_key, model, max(ai_limit - stats["ai"] - stats["ai_failed"], 0), limiter=limiter)
                    stats["ai"] += enrichment.enriched
                    stats["ai_failed"] += enrichment.failed
                if writer:
                    export_products(writer, batch)
                if apply:
                    upsert_products(conn, batch, run_id)
                    upsert_normalized_catalog(conn, batch, run_id)
                stats["eligible"] += len(batch)
        if apply:
            for advertiser_id in seen_advertisers:
                stale = conn.execute("DELETE FROM prodotti WHERE source = 'awin' AND advertiser_id = ? AND (last_seen_run IS NULL OR last_seen_run <> ?)", (advertiser_id, run_id))
                stats["deleted"] += max(stale.rowcount or 0, 0)
                mark_missing_offers_unavailable(conn, advertiser_id, run_id)
            conn.execute("UPDATE feed_import_runs SET finished_at = ?, processed_count = ?, imported_count = ?, deleted_count = ?, ai_count = ?, status = 'success' WHERE run_id = ?", (datetime.now(timezone.utc).isoformat(), stats["received"], stats["eligible"], stats["deleted"], stats["ai"], run_id))
    finally:
        if export_handle:
            export_handle.close()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Pulisce e importa il feed Awin locale.")
    parser.add_argument("--apply", action="store_true", help="Scrive nel database e rimuove gli articoli non disponibili.")
    parser.add_argument("--ai-limit", type=int, default=500, help="Massimo di prodotti ambigui inviati a Gemini per esecuzione (predefinito: 500).")
    parser.add_argument("--export-csv", type=Path, help="Crea anche un CSV UTF-8 pulito nel percorso indicato.")
    parser.add_argument("--bootstrap-limit", type=int, help="Crea un catalogo iniziale bilanciato tra i merchant del feed.")
    parser.add_argument("--replace-catalog", action="store_true", help="Con bootstrap, elimina demo e precedenti prodotti Awin prima di importare il campione curato.")
    parser.add_argument("--refresh-display-titles", action="store_true", help="Pulisce i titoli già nel database, senza download o chiamate IA.")
    args = parser.parse_args()
    if args.refresh_display_titles:
        print("TITOLI RIPULITI")
        print(f"updated: {refresh_display_titles()}")
        return
    if args.bootstrap_limit:
        stats = bootstrap_clean_catalog(limit=max(args.bootstrap_limit, 1), ai_limit=max(args.ai_limit, 0), export_csv=args.export_csv, replace_catalog=args.replace_catalog)
        print("CATALOGO INIZIALE CURATO")
    else:
        stats = sync(apply=args.apply, ai_limit=max(args.ai_limit, 0), export_csv=args.export_csv)
        print("IMPORTAZIONE" if args.apply else "ANTEPRIMA (nessuna scrittura)")
    for key in ("received", "eligible", "selected", "removed_unavailable", "skipped_invalid", "ai", "ai_failed", "deleted"):
        print(f"{key}: {stats[key]}")


if __name__ == "__main__":
    main()
