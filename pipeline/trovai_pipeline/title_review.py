"""Titoli utente generati da Gemini per il catalogo già importato.

Non riscarica il feed e non modifica mai ``source_title`` o ``description``.
Gemini formula il titolo visibile di OGNI prodotto; il programma locale non lo
riscrive. Le regole locali servono solo a estrarre/validare attributi e a
rifiutare, senza alterarlo, un risultato strutturalmente non utilizzabile.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from google import genai
from google.genai import types

from trovai_pipeline.config import load_secrets, project_root
from trovai_pipeline.database import connect_database, database_settings
from trovai_pipeline.gemini import RateLimiter, call_with_retry
from trovai_pipeline.schema import ensure_prodotti_table
from trovai_pipeline.feed_cleaner import (
    _AGE_GROUP_RULES,
    _COLOR_RULES,
    _GENDER_RULES,
    _MATERIAL_RULES,
    _known_canonical_value,
    clean_title,
    normalized_text,
)
from trovai_pipeline.awin_sync import feed_enrichment_settings


MODEL_NAME = "gemini-3.5-flash-lite"
# Free Tier: 15 generate_content requests/minuto per questo modello. Venti
# prodotti in una richiesta riducono il numero totale di chiamate; 4,3 secondi
# fra le richieste mantengono il ritmo sotto il limite anche su esecuzioni lunghe.
BATCH_SIZE = 20
MIN_SECONDS_BETWEEN_REQUESTS = 4.3
MAX_RATE_LIMIT_RETRIES = 4
TRAILING_WORDS = {"in", "di", "da", "con", "per", "e", "ed", "o", "and", "or", "with", "for", "made"}


def _terms(rules: Iterable[tuple[str, ...]]) -> set[str]:
    return {term for _, *values in rules for term in values if len(term) > 2}


ATTRIBUTE_TERMS = _terms(_COLOR_RULES) | _terms(_MATERIAL_RULES) | _terms(_GENDER_RULES) | _terms(_AGE_GROUP_RULES)
ATTRIBUTE_TERMS |= {"militare", "tessuto", "intrecciato", "intrecciata", "mesh", "suede", "scamosciato", "scamosciata"}


def title_issues(title: str | None, *, brand: str | None, color: str | None,
                 material: str | None, gender: str | None, age_group: str | None) -> list[str]:
    """Segnala errori gravi, senza riscrivere il titolo proposto da Gemini."""
    text = normalized_text(title) or ""
    if not text:
        return ["titolo_vuoto"]
    words = text.split()
    reasons: list[str] = []
    if words and words[-1] in TRAILING_WORDS:
        reasons.append("connettivo_finale")
    padded = f" {text} "
    # La marca puo far parte del modello (per esempio "Jordan 3 Retro"). Non
    # la trattiamo come errore: Gemini decide se mantenerla per chiarezza.
    if any(f" {term} " in padded for term in ATTRIBUTE_TERMS):
        reasons.append("attributo_nel_titolo")
    if re.search(r"\b(?:in|di|da|con|per)\s*$", text):
        reasons.append("preposizione_finale")
    return list(dict.fromkeys(reasons))


def ensure_review_schema(conn) -> None:
    ensure_prodotti_table(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS title_quality_reviews (
            id BIGSERIAL PRIMARY KEY,
            product_row_id BIGINT NOT NULL,
            source_title TEXT NOT NULL,
            previous_title TEXT,
            final_title TEXT,
            issues_json JSONB NOT NULL,
            model_name TEXT,
            status TEXT NOT NULL,
            reviewed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS title_quality_reviews_product_idx ON title_quality_reviews(product_row_id)")


def _json_text(response_text: str | None) -> list[dict[str, Any]]:
    raw = (response_text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
    value = json.loads(raw)
    return value if isinstance(value, list) else []


def review_batch(client: genai.Client, rows: list[dict[str, Any]], model: str) -> dict[int, dict[str, Any]]:
    payload = [
        {
            "id": row["id"],
            "source_title": row["source_title"],
            "current_title": row["title"],
            "description": row["description"],
            "brand": row["brand"],
            "color": row["color"],
            "material": row["material"],
            "gender": row["gender"],
            "age_group": row["age_group"],
            "problems": row["issues"],
        }
        for row in rows
    ]
    prompt = """Sei il controllo qualità finale di un catalogo moda italiano.
Restituisci SOLO un array JSON. Per ogni id restituisci esattamente:
id, visible_title, suggested_color, suggested_material, suggested_gender, suggested_age_group.

Compito:
- Leggi titolo originale, descrizione e campi disponibili. Correggi il solo
  visible_title affinche sia breve, grammaticale e chiaramente comprensibile.
- visible_title e' il nome che vede l'utente: NON deve contenere colore,
  taglia, materiale, genere, fascia d'eta, prezzo, disponibilita, promozioni,
  connettivi finali o frammenti come "in", "con", "e".
- Quando il brand e' parte inscindibile del nome del modello (per esempio
  "Jordan 3 Retro"), puoi mantenerlo nel visible_title. Non aggiungere invece
  una marca separata soltanto per ripetere il campo brand.
- I nomi commerciali di colorazione, anche in inglese, non sono il modello:
  rimuovi parole come white, blue, black, ivory, platinum, orange, purple,
  maroon, cream, green, red, grey e simili dal visible_title e restituiscile,
  se supportate, in suggested_color. Esempio: "Dunk High Summit White Pure
  Platinum" deve diventare "Dunk High".
- Se manca un modello preciso, conserva il tipo di capo e gli eventuali codici
  o numeri che identificano realmente il modello. Esempio: "Pantaloni Jean 19
  Militare in" -> "Pantaloni Jeans 19".
- Compila suggested_* SOLO se il valore e' esplicito nel titolo, descrizione o
  dati ricevuti; altrimenti usa null. Non inventare mai materiale o colore.
- Per colore usa italiano semplice, ad esempio verde; "militare" e' verde solo
  se indica chiaramente la tonalita del capo. I campi suggeriti non devono
  apparire nel visible_title.
- Non cambiare la marca e non aggiungere informazioni non verificabili.

Righe da controllare:\n""" + json.dumps(payload, ensure_ascii=False)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
    )
    allowed = {row["id"] for row in rows}
    return {
        int(item["id"]): item
        for item in _json_text(response.text)
        if isinstance(item, dict) and str(item.get("id", "")).isdigit() and int(item["id"]) in allowed
    }


def review_batch_with_retry(client: genai.Client, rows: list[dict[str, Any]], model: str,
                            limiter: RateLimiter | None = None) -> dict[int, dict[str, Any]]:
    """Rispetta il rate limit e ritenta il medesimo blocco, senza saltarlo."""
    return call_with_retry(lambda: review_batch(client, rows, model), limiter=limiter,
                           max_retries=MAX_RATE_LIMIT_RETRIES)


def _safe_suggestion(value: Any, rules: Iterable[tuple[str, ...]]) -> str | None:
    return _known_canonical_value(normalized_text(value), rules)


def refresh_parent_titles(conn) -> None:
    """Propaga il titolo validato all'albero senza toccare offerte e varianti."""
    conn.execute("""
        UPDATE catalog_products AS products
        SET canonical_title = CASE
                WHEN chosen.brand IS NULL OR BTRIM(chosen.brand) = '' THEN chosen.title
                WHEN POSITION(LOWER(chosen.brand) IN LOWER(chosen.title)) > 0 THEN chosen.title
                ELSE chosen.title || ' ' || chosen.brand
            END,
            clean_title = chosen.clean_title,
            source_title = chosen.source_title,
            updated_at = CURRENT_TIMESTAMP
        FROM (
            SELECT DISTINCT ON (variants.product_id)
                variants.product_id, legacy.title, legacy.clean_title,
                legacy.source_title, legacy.brand
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


def run_review(*, apply: bool, limit: int) -> dict[str, int]:
    secrets = load_secrets()
    settings = database_settings(project_root(), secrets)
    if settings.backend != "postgres":
        raise RuntimeError("Configura PostgreSQL prima del controllo qualità titoli.")
    api_key, _ = feed_enrichment_settings(secrets)
    # Questo revisore e' indipendente dal modello configurato per importare il
    # feed: utilizza il modello Flash-Lite attualmente disponibile ai progetti
    # nuovi, salvo una scelta esplicita nel file dei segreti.
    model = str(secrets.get("TITLE_REVIEW_MODEL", MODEL_NAME)).strip() or MODEL_NAME
    stats = {"scanned": 0, "already_completed": 0, "queued": 0, "reviewed": 0, "updated": 0, "rejected": 0, "failed": 0}

    with connect_database(settings) as conn:
        ensure_review_schema(conn)
        stats["scanned"] = conn.execute("SELECT COUNT(*) FROM prodotti WHERE source = 'awin'").fetchone()[0]
        rows = conn.execute("""
            SELECT id, title, source_title, description, brand, color, material, gender, age_group
            FROM prodotti AS products
            WHERE source = 'awin'
              AND NOT EXISTS (
                SELECT 1
                FROM title_quality_reviews AS reviews
                WHERE reviews.product_row_id = products.id
                  AND reviews.source_title = COALESCE(products.source_title, products.title, '')
                  AND reviews.status = 'accepted'
              )
            ORDER BY id
        """).fetchall()
        candidates: list[dict[str, Any]] = []
        for row in rows:
            item = {
                "id": row[0], "title": row[1] or "", "source_title": row[2] or row[1] or "",
                "description": row[3], "brand": row[4], "color": row[5], "material": row[6],
                "gender": row[7], "age_group": row[8],
            }
            item["issues"] = title_issues(
                item["title"], brand=item["brand"], color=item["color"], material=item["material"],
                gender=item["gender"], age_group=item["age_group"],
            )
            # Ogni prodotto, anche se le regole non trovano anomalie, riceve
            # un titolo formulato da Gemini: Gemini e' la fonte del titolo
            # utente, non un correttore chiamato solo in casi eccezionali.
            candidates.append(item)
        stats["already_completed"] = stats["scanned"] - len(candidates)
        candidates = candidates[:limit]
        stats["queued"] = len(candidates)
        if not apply:
            return stats
        if not api_key:
            raise RuntimeError("Manca una chiave Gemini per la revisione titoli. Configura GEMINI_VISION_API_KEY o GEMINI_FEED_API_KEY.")

        client = genai.Client(api_key=api_key)
        limiter = RateLimiter(MIN_SECONDS_BETWEEN_REQUESTS)
        for start in range(0, len(candidates), BATCH_SIZE):
            batch = candidates[start:start + BATCH_SIZE]
            try:
                reviewed = review_batch_with_retry(client, batch, model, limiter)
            except Exception as exc:
                stats["failed"] += len(batch)
                print(f"ERRORE batch titoli {start + 1}-{start + len(batch)}: {exc}")
                continue
            for item in batch:
                result = reviewed.get(item["id"])
                if result is None:
                    stats["failed"] += 1
                    continue
                stats["reviewed"] += 1
                color = item["color"] or _safe_suggestion(result.get("suggested_color"), _COLOR_RULES)
                material = item["material"] or _safe_suggestion(result.get("suggested_material"), _MATERIAL_RULES)
                gender = item["gender"] or _safe_suggestion(result.get("suggested_gender"), _GENDER_RULES)
                age_group = item["age_group"] or _safe_suggestion(result.get("suggested_age_group"), _AGE_GROUP_RULES)
                # Questo e' esattamente il testo formulato da Gemini. Non
                # applichiamo sostituzioni, title-case o pulizie locali che ne
                # possano modificare la grammatica; togliamo solo caratteri di
                # controllo invisibili.
                proposed = re.sub(r"[\x00-\x1f\x7f]+", " ", str(result.get("visible_title") or ""))
                proposed = re.sub(r"\s+", " ", proposed).strip()
                remaining = title_issues(proposed, brand=item["brand"], color=color, material=material,
                                         gender=gender, age_group=age_group)
                status = "accepted" if not remaining else "rejected_local_validation"
                conn.execute("""
                    INSERT INTO title_quality_reviews (
                        product_row_id, source_title, previous_title, final_title,
                        issues_json, model_name, status, reviewed_at
                    ) VALUES (?, ?, ?, ?, CAST(? AS JSONB), ?, ?, ?)
                """, (
                    item["id"], item["source_title"], item["title"], proposed,
                    json.dumps({"initial": item["issues"], "remaining": remaining}, ensure_ascii=False),
                    model, status, datetime.now(timezone.utc),
                ))
                if remaining:
                    stats["rejected"] += 1
                    continue
                conn.execute("""
                    UPDATE prodotti
                    SET title = ?, clean_title = ?, color = ?, material = ?, gender = ?, age_group = ?,
                        data_quality = 'title_quality_checked'
                    WHERE id = ?
                """, (proposed, clean_title(proposed), color, material, gender, age_group, item["id"]))
                stats["updated"] += 1
        refresh_parent_titles(conn)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Fa formulare a Gemini il titolo utente di ogni prodotto Awin.")
    parser.add_argument("--apply", action="store_true", help="Esegue Gemini su ogni prodotto e salva solo titoli che superano il controllo strutturale.")
    parser.add_argument("--limit", type=int, default=1000, help="Massimo prodotti da revisionare (predefinito: 1000).")
    args = parser.parse_args()
    if args.limit < 1:
        raise SystemExit("limit deve essere almeno 1.")
    stats = run_review(apply=args.apply, limit=args.limit)
    print("REVISIONE TITOLI" if args.apply else "ANTEPRIMA REVISIONE TITOLI")
    for key, value in stats.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
