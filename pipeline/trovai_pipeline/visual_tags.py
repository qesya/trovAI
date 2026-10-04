"""Test controllato: crea tag visivi per le stesse 10 immagini vettorizzate.

I tag vengono salvati separatamente dai dati dichiarati dal merchant. Non
sostituiscono brand, taglia, EAN, prezzo, disponibilita o composizione ufficiale.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

# Carichiamo PostgreSQL prima del client Google: sul PC questo evita che la
# policy di integrita di Windows blocchi in modo intermittente la DLL psycopg.
from trovai_pipeline.config import load_secrets, project_root
from trovai_pipeline.database import connect_database, database_settings
from trovai_pipeline.image_embeddings import (
    EmbeddingTestError,
    download_image,
    selected_offers,
)
from google import genai
from google.genai import types


# Modello consigliato dalla risposta ufficiale dell'API per i nuovi progetti.
MODEL_NAME = "gemini-3.5-flash-lite"


class VisualTags(BaseModel):
    """Solo osservazioni visive: valori in italiano, senza informazioni inventate."""

    colore_principale: str = Field(description="Colore visivo dominante, oppure 'sconosciuto'.")
    colori_visibili: list[str] = Field(description="Da zero a cinque colori chiaramente visibili.")
    materiale_visivo: str = Field(description="Tessuto/aspetto visivo, oppure 'sconosciuto'. Non e una composizione ufficiale.")
    confidenza_materiale: Literal["alta", "media", "bassa", "sconosciuta"]
    stile: list[str] = Field(description="Da zero a quattro tag di stile in italiano, per esempio sneaker o streetwear.")
    motivo: list[str] = Field(description="Motivi visibili, per esempio righe o tinta unita.")
    dettagli_visivi: list[str] = Field(description="Da zero a cinque dettagli chiaramente visibili, per esempio swoosh o suola a contrasto.")
    confidenza_generale: int = Field(ge=0, le=100, description="Sicurezza complessiva della lettura visiva, da 0 a 100.")


PROMPT = """
Analizza solamente cio che e chiaramente visibile nella foto di un singolo prodotto moda.
Restituisci tutti i valori in italiano e rispetta lo schema JSON.

Regole rigorose:
- Non inventare informazioni non visibili.
- Non dedurre o restituire taglia, prezzo, disponibilita, EAN, composizione ufficiale,
  genere, fascia di eta o nome esatto del modello.
- materiale_visivo descrive solo l'aspetto: scrivi 'sconosciuto' se non e distinguibile.
- Per un logo o dettaglio di brand, inseriscilo solo se e chiaramente riconoscibile.
- I colori devono essere semplici e utilizzabili come filtro: bianco, nero, blu, rosso,
  verde, giallo, rosa, viola, arancione, marrone, grigio, beige, oro, argento,
  multicolore oppure sconosciuto.
- Se l'immagine non e chiara, usa liste vuote, 'sconosciuto' e una confidenza bassa.
""".strip()


def ensure_visual_tag_schema(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_visual_tags (
            id BIGSERIAL PRIMARY KEY,
            offer_id BIGINT NOT NULL REFERENCES merchant_offers(id) ON DELETE CASCADE,
            color_variant_id BIGINT REFERENCES product_color_variants(id) ON DELETE SET NULL,
            image_sha256 TEXT NOT NULL,
            model_name TEXT NOT NULL,
            colore_principale TEXT NOT NULL,
            materiale_visivo TEXT NOT NULL,
            confidenza_materiale TEXT NOT NULL,
            confidenza_generale INTEGER NOT NULL,
            tags_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(offer_id, image_sha256, model_name)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS product_visual_tags_offer_idx ON product_visual_tags(offer_id)")


def already_tagged(conn, offer_id: int, image_hash: str) -> bool:
    row = conn.execute("""
        SELECT 1 FROM product_visual_tags
        WHERE offer_id = ? AND image_sha256 = ? AND model_name = ?
    """, (offer_id, image_hash, MODEL_NAME)).fetchone()
    return row is not None


def analyze_image(client: genai.Client, image_bytes: bytes, mime_type: str) -> VisualTags:
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[PROMPT, types.Part.from_bytes(data=image_bytes, mime_type=mime_type)],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=VisualTags,
            temperature=0,
        ),
    )
    if response.parsed is None:
        raise EmbeddingTestError("Gemini non ha restituito tag visivi strutturati.")
    return VisualTags.model_validate(response.parsed)


def run_test(*, dry_run: bool, force: bool) -> dict[str, int]:
    secrets = load_secrets()
    api_key = str(secrets.get("GEMINI_VISION_API_KEY", "")).strip()
    if not api_key:
        raise EmbeddingTestError(
            "Manca GEMINI_VISION_API_KEY in .streamlit/secrets.toml. Non incollare la chiave nel terminale."
        )
    settings = database_settings(project_root(), secrets)
    if settings.backend != "postgres":
        raise EmbeddingTestError("Il test richiede la configurazione PostgreSQL locale di TrovAI.")

    stats = {"selected": 0, "created": 0, "already_present": 0, "failed": 0}
    client = None if dry_run else genai.Client(api_key=api_key)
    with connect_database(settings) as conn:
        ensure_visual_tag_schema(conn)
        offers = selected_offers(conn)
        stats["selected"] = len(offers)
        for offer_id, color_variant_id, url, label in offers:
            try:
                image_bytes, mime_type = download_image(url)
                image_hash = hashlib.sha256(image_bytes).hexdigest()
                if not force and already_tagged(conn, offer_id, image_hash):
                    stats["already_present"] += 1
                    print(f"Gia presente, nessuna nuova chiamata: {label}")
                    continue
                if dry_run:
                    print(f"PRONTO: {label} ({mime_type}, {len(image_bytes) / 1024:.0f} KB)")
                    continue
                tags = analyze_image(client, image_bytes, mime_type)
                payload = tags.model_dump()
                conn.execute("""
                    INSERT INTO product_visual_tags (
                        offer_id, color_variant_id, image_sha256, model_name,
                        colore_principale, materiale_visivo, confidenza_materiale,
                        confidenza_generale, tags_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CAST(? AS JSONB), ?)
                    ON CONFLICT(offer_id, image_sha256, model_name)
                    DO UPDATE SET colore_principale = excluded.colore_principale,
                                  materiale_visivo = excluded.materiale_visivo,
                                  confidenza_materiale = excluded.confidenza_materiale,
                                  confidenza_generale = excluded.confidenza_generale,
                                  tags_json = excluded.tags_json,
                                  created_at = excluded.created_at
                """, (
                    offer_id, color_variant_id, image_hash, MODEL_NAME,
                    tags.colore_principale, tags.materiale_visivo,
                    tags.confidenza_materiale, tags.confidenza_generale,
                    json.dumps(payload, ensure_ascii=False), datetime.now(timezone.utc),
                ))
                stats["created"] += 1
                print(
                    f"OK: {label} — colore: {tags.colore_principale}; "
                    f"materiale visivo: {tags.materiale_visivo}; "
                    f"confidenza: {tags.confidenza_generale}%"
                )
                time.sleep(0.5)
            except Exception as exc:
                stats["failed"] += 1
                print(f"ERRORE: {label} — {exc}")
                message = str(exc).lower()
                if (
                    "402" in message
                    or "prepayment credits are depleted" in message
                    or "429" in message
                    or "404" in message
                    or "not_found" in message
                ):
                    print("ARRESTO: modello, quota o credito Gemini non disponibile. Nessuna altra immagine viene inviata.")
                    break
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Crea tag visivi solo per 10 immagini campione.")
    parser.add_argument("--dry-run", action="store_true", help="Verifica immagini e database senza chiamare Gemini.")
    parser.add_argument("--force", action="store_true", help="Rigenera anche tag gia salvati: puo consumare quota.")
    args = parser.parse_args()
    stats = run_test(dry_run=args.dry_run, force=args.force)
    print("\nTEST TAG VISIVI" if not args.dry_run else "\nANTEPRIMA TEST TAG VISIVI")
    for key in ("selected", "created", "already_present", "failed"):
        print(f"{key}: {stats[key]}")


if __name__ == "__main__":
    main()
