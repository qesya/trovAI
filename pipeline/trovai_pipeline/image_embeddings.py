"""Test controllato: crea embedding visivi per sole 10 immagini del catalogo.

Non modifica prodotti, offerte o schermate Streamlit. I vettori sono salvati
in una tabella separata, cosi il test puo essere verificato o eliminato senza
toccare il catalogo Awin.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import truststore

# Deve avvenire prima dell'import di google-genai/httpx: cosi anche il client
# Gemini usa le CA fidate da Windows, mantenendo integra la verifica HTTPS.
truststore.inject_into_ssl()

from google import genai
from google.genai import types

from trovai_pipeline.config import load_secrets, project_root
from trovai_pipeline.database import connect_database, database_settings


MODEL_NAME = "gemini-embedding-2"
DIMENSIONS = 1536
MAX_IMAGE_BYTES = 12 * 1024 * 1024

# Dieci immagini scelte apposta: 3 Boris Firenze, 3 OneStreet, 4 Costumein.
# Sono tutte JPEG/PNG, i formati immagine supportati dal modello.
SAMPLE_PRODUCTS = (
    (124556, "58436850516303", "Boris Firenze — Energy Lime"),
    (124556, "58436860543311", "Boris Firenze — Energy White"),
    (124556, "58436864999759", "Boris Firenze — Estella White"),
    (128805, "46680781750611", "OneStreet — Jordan 1 Low Bred Toe"),
    (128805, "46487478108499", "OneStreet — Jordan 1 Mid Grey Green"),
    (128805, "46676617593171", "OneStreet — Jordan 1 Mid Chicago 2020"),
    (126191, "58748950937949", "Costumein — Blazer Antoine"),
    (126191, "58690977071453", "Costumein — Camicia Andrea a righe"),
    (126191, "64663248830813", "Costumein — Jeans beige"),
    (126191, "64805257347421", "Costumein — T-shirt baby pink"),
)


class EmbeddingTestError(RuntimeError):
    """Errore mostrato in modo comprensibile durante il test."""



def ensure_embedding_schema(conn) -> None:
    """Crea una tabella indipendente dal catalogo per il solo test vettoriale."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_image_embeddings (
            id BIGSERIAL PRIMARY KEY,
            offer_id BIGINT NOT NULL REFERENCES merchant_offers(id) ON DELETE CASCADE,
            color_variant_id BIGINT REFERENCES product_color_variants(id) ON DELETE SET NULL,
            image_link TEXT NOT NULL,
            image_sha256 TEXT NOT NULL,
            model_name TEXT NOT NULL,
            dimensions INTEGER NOT NULL,
            embedding_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(offer_id, image_sha256, model_name, dimensions)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS product_image_embeddings_offer_idx ON product_image_embeddings(offer_id)")


def selected_offers(conn) -> list[tuple[int, int | None, str, str]]:
    """Restituisce le dieci offerte scelte, nell'ordine dichiarato sopra."""
    selected: list[tuple[int, int | None, str, str]] = []
    for advertiser_id, source_product_id, label in SAMPLE_PRODUCTS:
        row = conn.execute("""
            SELECT offers.id, variants.color_variant_id, offers.image_link
            FROM merchant_offers AS offers
            JOIN product_variants AS variants ON variants.id = offers.variant_id
            WHERE offers.advertiser_id = ?
              AND offers.source_product_id = ?
              AND offers.availability = TRUE
        """, (advertiser_id, source_product_id)).fetchone()
        if row is None:
            raise EmbeddingTestError(f"Prodotto campione non trovato o non disponibile: {label}.")
        if not row[2]:
            raise EmbeddingTestError(f"Immagine mancante nel feed: {label}.")
        selected.append((row[0], row[1], str(row[2]), label))
    return selected


def image_mime_type(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    raise EmbeddingTestError("L'immagine scaricata non e JPEG o PNG; il test la salta senza inviarla a Gemini.")


def download_image(url: str) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "TrovAI-Embedding-Pilot/1.0"})
    try:
        # Mantiene la verifica HTTPS attiva usando l'archivio certificati di
        # Windows. Non accetta certificati insicuri e funziona anche con una
        # CA aziendale/antivirus già considerata attendibile da Windows.
        ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        with urllib.request.urlopen(request, timeout=45, context=ssl_context) as response:
            data = response.read(MAX_IMAGE_BYTES + 1)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        raise EmbeddingTestError(f"Download immagine non riuscito: {exc}") from exc
    if len(data) > MAX_IMAGE_BYTES:
        raise EmbeddingTestError("L'immagine supera 12 MB e non viene inviata a Gemini.")
    return data, image_mime_type(data)


def already_embedded(conn, offer_id: int, image_hash: str) -> bool:
    row = conn.execute("""
        SELECT 1 FROM product_image_embeddings
        WHERE offer_id = ? AND image_sha256 = ? AND model_name = ? AND dimensions = ?
    """, (offer_id, image_hash, MODEL_NAME, DIMENSIONS)).fetchone()
    return row is not None


def create_embedding(client: genai.Client, image_bytes: bytes, mime_type: str) -> list[float]:
    result = client.models.embed_content(
        model=MODEL_NAME,
        contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime_type)],
        config=types.EmbedContentConfig(output_dimensionality=DIMENSIONS),
    )
    if not result.embeddings:
        raise EmbeddingTestError("Gemini non ha restituito alcun vettore per l'immagine.")
    vector = list(result.embeddings[0].values or [])
    if len(vector) != DIMENSIONS:
        raise EmbeddingTestError(
            f"Gemini ha restituito un vettore di {len(vector)} numeri, attesi {DIMENSIONS}."
        )
    return vector


def run_test(*, dry_run: bool, force: bool) -> dict[str, int]:
    secrets = load_secrets()
    api_key = str(secrets.get("GEMINI_EMBEDDING_API_KEY", "")).strip()
    if not api_key:
        raise EmbeddingTestError(
            "Manca GEMINI_EMBEDDING_API_KEY nel file .env (o come variabile d'ambiente). Non incollare la chiave nel terminale."
        )
    settings = database_settings(project_root(), secrets)
    if settings.backend != "postgres":
        raise EmbeddingTestError("Il test richiede la configurazione PostgreSQL locale di TrovAI.")

    stats = {"selected": 0, "created": 0, "already_present": 0, "failed": 0}
    client = None if dry_run else genai.Client(api_key=api_key)
    with connect_database(settings) as conn:
        ensure_embedding_schema(conn)
        offers = selected_offers(conn)
        stats["selected"] = len(offers)
        for offer_id, color_variant_id, url, label in offers:
            try:
                image_bytes, mime_type = download_image(url)
                image_hash = hashlib.sha256(image_bytes).hexdigest()
                if not force and already_embedded(conn, offer_id, image_hash):
                    stats["already_present"] += 1
                    print(f"Gia presente, nessuna nuova chiamata: {label}")
                    continue
                if dry_run:
                    print(f"PRONTO: {label} ({mime_type}, {len(image_bytes) / 1024:.0f} KB)")
                    continue
                vector = create_embedding(client, image_bytes, mime_type)
                conn.execute("""
                    INSERT INTO product_image_embeddings (
                        offer_id, color_variant_id, image_link, image_sha256,
                        model_name, dimensions, embedding_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, CAST(? AS JSONB), ?)
                    ON CONFLICT(offer_id, image_sha256, model_name, dimensions)
                    DO UPDATE SET embedding_json = excluded.embedding_json,
                                  created_at = excluded.created_at
                """, (
                    offer_id, color_variant_id, url, image_hash, MODEL_NAME,
                    DIMENSIONS, json.dumps(vector), datetime.now(timezone.utc),
                ))
                stats["created"] += 1
                preview = ", ".join(f"{value:.5f}" for value in vector[:8])
                print(f"OK: {label} — {len(vector)} numeri. Anteprima: [{preview}, ...]")
                time.sleep(0.4)
            except (EmbeddingTestError, Exception) as exc:
                stats["failed"] += 1
                print(f"ERRORE: {label} — {exc}")
                # Un 402 significa che Google non accettera altre richieste
                # finche non esiste credito prepagato: fermarsi qui evita
                # tentativi ripetuti e rende il problema immediatamente chiaro.
                if "402" in str(exc) or "prepayment credits are depleted" in str(exc).lower():
                    print("ARRESTO: credito Gemini non disponibile. Nessuna altra immagine viene inviata.")
                    break
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Crea embedding visivi soltanto per 10 immagini campione.")
    parser.add_argument("--dry-run", action="store_true", help="Verifica immagini e database senza chiamare Gemini.")
    parser.add_argument("--force", action="store_true", help="Rigenera anche vettori gia salvati: puo generare nuovi costi.")
    args = parser.parse_args()
    stats = run_test(dry_run=args.dry_run, force=args.force)
    print("\nTEST EMBEDDING" if not args.dry_run else "\nANTEPRIMA TEST EMBEDDING")
    for key in ("selected", "created", "already_present", "failed"):
        print(f"{key}: {stats[key]}")


if __name__ == "__main__":
    main()
