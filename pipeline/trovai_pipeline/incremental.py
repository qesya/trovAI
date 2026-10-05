"""Aggiornamento incrementale del catalogo: confronto con il database prima dell'IA.

Ogni riga del feed viene classificata con regole deterministiche, prima di
qualsiasi chiamata a Gemini:

* ``new``        offerta mai vista per quel negozio;
* ``unchanged``  stessa impronta dei contenuti e dei campi operativi;
* ``updated``    cambiano solo prezzo, taglie, link, immagine o EAN;
* ``reactivated`` offerta tornata disponibile (con o senza altri cambi operativi);
* ``content``    cambiano i contenuti usati dall'IA (titolo, descrizione, marca,
                 categoria, colore, materiale, genere): unico caso, insieme a
                 ``new``, che puo' arrivare a Gemini.

Identita' (senza IA): l'offerta e' ``negozio + EAN`` quando l'EAN e' valido,
altrimenti ``negozio + ID prodotto del negozio``. Un'offerta trovata per ID che
riceve un EAN in seguito resta la stessa offerta.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from trovai_pipeline.feed_cleaner import NORMALIZATION_VERSION, CleanProduct
from trovai_pipeline.normalized_catalog import attach_ean_to_variant

NEW, UNCHANGED, UPDATED, REACTIVATED, CONTENT = "new", "unchanged", "updated", "reactivated", "content"

# Un lavoro IA fallito viene ritentato automaticamente al massimo 3 volte.
MAX_AI_ATTEMPTS = 3
# Un lavoro "running" piu' vecchio di cosi' e' considerato abbandonato (processo morto).
STALE_AI_CLAIM = timedelta(minutes=30)
# Chiave del lock PostgreSQL che impedisce due importazioni contemporanee.
SYNC_LOCK_KEY = 74_830_201


@dataclass(frozen=True)
class ExistingOffer:
    id: int
    source_product_id: str
    ean: str | None
    semantic_hash: str | None
    operational_hash: str | None
    availability: bool


def identity_key(product: CleanProduct) -> tuple[int, str]:
    """Chiave usata per riconoscere le righe duplicate nella stessa importazione."""
    return (product.advertiser_id, f"ean:{product.ean}" if product.ean else f"id:{product.source_product_id}")


def fetch_existing_offers(conn, products: list[CleanProduct]) -> dict[int, ExistingOffer]:
    """Trova le offerte gia' salvate con due sole query (EAN, poi ID del negozio)."""
    if not products:
        return {}
    columns = "id, advertiser_id, source_product_id, ean, semantic_hash, operational_hash, availability"
    by_ean: dict[tuple[int, str], ExistingOffer] = {}
    with_ean = [product for product in products if product.ean]
    if with_ean:
        rows = conn.execute(
            f"""SELECT {columns} FROM merchant_offers
                WHERE ean IS NOT NULL AND (advertiser_id, ean) IN (
                    SELECT * FROM unnest(?::integer[], ?::text[]))
                ORDER BY id""",
            ([product.advertiser_id for product in with_ean], [product.ean for product in with_ean]),
        ).fetchall()
        for row in rows:
            by_ean.setdefault((row[1], row[3]), _offer(row))
    rows = conn.execute(
        f"""SELECT {columns} FROM merchant_offers
            WHERE (advertiser_id, source_product_id) IN (
                SELECT * FROM unnest(?::integer[], ?::text[]))""",
        ([product.advertiser_id for product in products], [product.source_product_id for product in products]),
    ).fetchall()
    by_source = {(row[1], row[2]): _offer(row) for row in rows}
    found: dict[int, ExistingOffer] = {}
    for index, product in enumerate(products):
        offer = (by_ean.get((product.advertiser_id, product.ean)) if product.ean else None) or by_source.get(
            (product.advertiser_id, product.source_product_id)
        )
        if offer is not None:
            found[index] = offer
    return found


def _offer(row) -> ExistingOffer:
    return ExistingOffer(
        id=row[0], source_product_id=row[2], ean=row[3], semantic_hash=row[4],
        operational_hash=row[5], availability=bool(row[6]),
    )


def classify(product: CleanProduct, offer: ExistingOffer | None) -> str:
    if offer is None:
        return NEW
    if offer.semantic_hash != product.content_hash:
        return CONTENT
    if not offer.availability:
        return REACTIVATED
    if offer.operational_hash != product.operational_hash:
        return UPDATED
    return UNCHANGED


def touch_unchanged(conn, products: list[CleanProduct], run_id: str) -> None:
    """Invariati: si segna solo che sono ancora nel feed. Nessun altro campo cambia."""
    if not products:
        return
    now = datetime.now(timezone.utc)
    conn.execute(
        "UPDATE merchant_offers SET last_seen_at = ?, last_seen_run = ? WHERE id = ANY(?)",
        (now, run_id, [product.offer_id for product in products]),
    )
    conn.execute(
        """UPDATE prodotti SET last_seen_run = ?
           WHERE source = 'awin' AND (advertiser_id, source_product_id) IN (
               SELECT * FROM unnest(?::integer[], ?::text[]))""",
        (run_id, [product.advertiser_id for product in products], [product.source_product_id for product in products]),
    )


def update_operational(conn, products: list[CleanProduct], run_id: str) -> None:
    """Prezzo, disponibilita', taglia, link, immagine ed EAN: scritti senza IA.

    Gli attributi arricchiti (marca, categoria, colore, titolo del modello...)
    non vengono toccati.
    """
    if not products:
        return
    now = datetime.now(timezone.utc)
    for product in products:
        attach_ean_to_variant(conn, product.offer_id, product.ean)
    conn.executemany(
        """UPDATE merchant_offers SET
               price = ?, sale_price = ?, currency = ?, advertiser_name = ?,
               merchant_deep_link = ?, aw_deep_link = ?, image_link = ?,
               ean = COALESCE(?, ean), operational_hash = ?, availability = TRUE,
               unavailable_since = NULL, last_seen_at = ?, last_seen_run = ?
           WHERE id = ?""",
        [
            (
                product.price, product.sale_price, product.currency, product.advertiser_name,
                product.merchant_deep_link, product.aw_deep_link, product.image_link,
                product.ean, product.operational_hash, now, run_id, product.offer_id,
            )
            for product in products
        ],
    )
    # La taglia disponibile e' un dato operativo: aggiorna la variante, se il feed la indica.
    conn.executemany(
        """UPDATE product_variants SET size = ?, updated_at = ?
           WHERE id = (SELECT variant_id FROM merchant_offers WHERE id = ?) AND size IS DISTINCT FROM ?""",
        [(product.size, now, product.offer_id, product.size) for product in products if product.size],
    )
    conn.executemany(
        """UPDATE prodotti SET
               price = ?, sale_price = ?, discount_percentage = ?, availability = 1,
               size = COALESCE(?, size), image_link = ?, merchant_deep_link = ?, aw_deep_link = ?,
               currency = ?, last_seen_run = ?
           WHERE source = 'awin' AND advertiser_id = ? AND source_product_id = ?""",
        [
            (
                product.price, product.sale_price, product.discount_percentage, product.size,
                product.image_link, product.merchant_deep_link, product.aw_deep_link,
                product.currency, run_id, product.advertiser_id, product.source_product_id,
            )
            for product in products
        ],
    )


def deactivate_prodotti(conn, advertiser_id: int, source_product_id: str | None = None, run_id: str | None = None) -> None:
    """Tabella storica ``prodotti``: stessa regola delle offerte, mai DELETE."""
    if source_product_id is not None:
        conn.execute(
            "UPDATE prodotti SET availability = 0, last_seen_run = COALESCE(?, last_seen_run) WHERE source = 'awin' AND advertiser_id = ? AND source_product_id = ?",
            (run_id, advertiser_id, source_product_id),
        )
        return
    conn.execute(
        "UPDATE prodotti SET availability = 0 WHERE source = 'awin' AND advertiser_id = ? AND availability = 1 AND last_seen_run IS DISTINCT FROM ?",
        (advertiser_id, run_id),
    )


# --- Stato delle elaborazioni IA --------------------------------------------------------

def ensure_ai_jobs_table(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feed_ai_jobs (
            content_hash TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            model TEXT,
            normalization_version TEXT,
            run_id TEXT,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
    """)


def _now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def mark_ai_pending(conn, hashes: Iterable[str]) -> None:
    """Prodotti che servono all'IA ma restano fuori (budget o chiave): da riprendere."""
    now = _now_text()
    conn.executemany(
        """INSERT INTO feed_ai_jobs (content_hash, status, normalization_version, updated_at)
           VALUES (?, 'pending', ?, ?) ON CONFLICT(content_hash) DO NOTHING""",
        [(value, NORMALIZATION_VERSION, now) for value in set(hashes)],
    )


def claim_ai_jobs(conn, hashes: Iterable[str], run_id: str | None, model: str) -> set[str]:
    """Prende in carico i lavori in modo atomico: due processi non elaborano lo stesso hash.

    Un hash gia' ``done`` o ``running`` (e non abbandonato) non viene restituito.
    """
    now = datetime.now(timezone.utc)
    stale = (now - STALE_AI_CLAIM).isoformat()
    claimed: set[str] = set()
    for value in dict.fromkeys(hashes):
        row = conn.execute(
            """INSERT INTO feed_ai_jobs (content_hash, status, attempts, model, normalization_version, run_id, updated_at)
               VALUES (?, 'running', 1, ?, ?, ?, ?)
               ON CONFLICT(content_hash) DO UPDATE SET
                   status = 'running', attempts = feed_ai_jobs.attempts + 1, model = excluded.model,
                   normalization_version = excluded.normalization_version, run_id = excluded.run_id,
                   updated_at = excluded.updated_at
               WHERE feed_ai_jobs.status IN ('pending', 'failed')
                  OR (feed_ai_jobs.status = 'running' AND feed_ai_jobs.updated_at < ?)
               RETURNING content_hash""",
            (value, model, NORMALIZATION_VERSION, run_id, now.isoformat(), stale),
        ).fetchone()
        if row:
            claimed.add(row[0])
    return claimed


def finish_ai_jobs(conn, done: Iterable[str], failed: Iterable[str], error: str | None = None,
                   prompt_tokens: int = 0, output_tokens: int = 0) -> None:
    now = _now_text()
    done = list(dict.fromkeys(done))
    conn.executemany(
        "UPDATE feed_ai_jobs SET status = 'done', last_error = NULL, updated_at = ? WHERE content_hash = ?",
        [(now, value) for value in done],
    )
    if done and (prompt_tokens or output_tokens):
        # I token sono del blocco: li attribuiamo al primo hash per non contarli piu' volte.
        conn.execute(
            "UPDATE feed_ai_jobs SET prompt_tokens = prompt_tokens + ?, output_tokens = output_tokens + ? WHERE content_hash = ?",
            (prompt_tokens, output_tokens, done[0]),
        )
    conn.executemany(
        "UPDATE feed_ai_jobs SET status = 'failed', last_error = ?, updated_at = ? WHERE content_hash = ?",
        [((error or "nessuna risposta per questo prodotto")[:500], now, value) for value in dict.fromkeys(failed)],
    )


def retryable_ai_hashes(conn, hashes: Iterable[str]) -> set[str]:
    """Hash rimasti in sospeso o falliti (entro i tentativi): da ritentare anche se invariati."""
    values = list(set(hashes))
    if not values:
        return set()
    rows = conn.execute(
        "SELECT content_hash FROM feed_ai_jobs WHERE content_hash = ANY(?) AND (status = 'pending' OR (status = 'failed' AND attempts < ?))",
        (values, MAX_AI_ATTEMPTS),
    ).fetchall()
    return {row[0] for row in rows}


def reset_failed_ai_jobs(conn) -> int:
    """Rimette in coda i lavori che hanno esaurito i tentativi automatici."""
    cursor = conn.execute("UPDATE feed_ai_jobs SET status = 'pending', attempts = 0 WHERE status = 'failed'")
    return max(cursor.rowcount or 0, 0)


# --- Lock dell'importazione ------------------------------------------------------------

def try_sync_lock(conn) -> bool:
    return bool(conn.execute("SELECT pg_try_advisory_lock(?)", (SYNC_LOCK_KEY,)).fetchone()[0])


def release_sync_lock(conn) -> None:
    conn.execute("SELECT pg_advisory_unlock(?)", (SYNC_LOCK_KEY,))
