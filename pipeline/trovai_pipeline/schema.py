"""Tabella ``prodotti``: una riga per offerta del feed, base del catalogo.

In origine la creava l'app Streamlit; ora e' la pipeline a crearla, cosi' un
database nuovo (CI, Neon, un altro PC) nasce completo. Su un database gia'
esistente non cambia nulla: aggiunge solo le colonne eventualmente mancanti.
"""

from __future__ import annotations

# (nome, tipo nella CREATE TABLE, tipo per ALTER su tabelle esistenti).
# Allineato allo schema originale dell'app (awin_db.py): stessi vincoli su un
# database nuovo; su uno esistente si aggiungono solo colonne, senza vincoli
# (ALTER ... NOT NULL fallirebbe sulle righe gia' presenti).
PRODOTTI_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("title", "TEXT NOT NULL", "TEXT"),
    ("source_title", "TEXT", "TEXT"),
    ("clean_title", "TEXT", "TEXT"),
    ("extracted_model", "TEXT", "TEXT"),
    ("description", "TEXT", "TEXT"),
    ("brand", "TEXT", "TEXT"),
    ("product_type", "TEXT", "TEXT"),
    ("sottocategoria", "TEXT", "TEXT"),
    ("gender", "TEXT", "TEXT"),
    ("age_group", "TEXT", "TEXT"),
    ("color", "TEXT", "TEXT"),
    ("size", "TEXT", "TEXT"),
    ("material", "TEXT", "TEXT"),
    ("price", "DOUBLE PRECISION NOT NULL CHECK (price >= 0)", "DOUBLE PRECISION"),
    ("sale_price", "DOUBLE PRECISION CHECK (sale_price IS NULL OR sale_price >= 0)", "DOUBLE PRECISION"),
    ("discount_percentage", "DOUBLE PRECISION", "DOUBLE PRECISION"),
    ("availability", "INTEGER NOT NULL CHECK (availability IN (0, 1))", "INTEGER"),
    ("condizione", "TEXT", "TEXT"),
    ("merchant", "TEXT NOT NULL", "TEXT"),
    ("image_link", "TEXT", "TEXT"),
    ("merchant_deep_link", "TEXT", "TEXT"),
    ("advertiser_id", "INTEGER", "INTEGER"),
    ("awin_feed_id", "TEXT", "TEXT"),
    ("merchant_product_id", "TEXT", "TEXT"),
    ("aw_deep_link", "TEXT", "TEXT"),
    ("currency", "TEXT NOT NULL DEFAULT 'EUR'", "TEXT"),
    ("source", "TEXT NOT NULL DEFAULT 'demo'", "TEXT"),
    ("source_updated_at", "TEXT", "TEXT"),
    ("imported_at", "TEXT", "TEXT"),
    ("ean", "TEXT", "TEXT"),
    ("source_product_id", "TEXT", "TEXT"),
    ("data_quality", "TEXT", "TEXT"),
    ("normalized_at", "TEXT", "TEXT"),
    ("last_seen_run", "TEXT", "TEXT"),
)


def ensure_prodotti_table(conn) -> None:
    """Crea ``prodotti`` se manca e aggiunge le colonne mancanti (idempotente)."""
    columns = ",\n            ".join(f"{name} {create_type}" for name, create_type, _ in PRODOTTI_COLUMNS)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS prodotti (
            id BIGSERIAL PRIMARY KEY,
            -- "<advertiser_id>:<EAN o id del feed>": chiave degli upsert.
            sku TEXT NOT NULL UNIQUE,
            {columns}
        )
    """)
    for name, _, alter_type in PRODOTTI_COLUMNS:
        conn.execute(f"ALTER TABLE prodotti ADD COLUMN IF NOT EXISTS {name} {alter_type}")
