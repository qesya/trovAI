"""Schema e migrazioni additive del catalogo prodotti."""

from __future__ import annotations

import sqlite3


AWIN_PRODUCT_COLUMNS = {
    "advertiser_id": "INTEGER",
    "awin_feed_id": "TEXT",
    "merchant_product_id": "TEXT",
    "aw_deep_link": "TEXT",
    "currency": "TEXT NOT NULL DEFAULT 'EUR'",
    "source": "TEXT NOT NULL DEFAULT 'demo'",
    "source_updated_at": "TEXT",
    "imported_at": "TEXT",
}


def ensure_awin_columns(conn: sqlite3.Connection) -> None:
    existing = {
        row[1] for row in conn.execute("PRAGMA table_info(prodotti)").fetchall()
    }
    if not existing:
        raise RuntimeError("La tabella prodotti non esiste")

    for name, definition in AWIN_PRODUCT_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE prodotti ADD COLUMN {name} {definition}")

    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_prodotti_awin_identity "
        "ON prodotti(advertiser_id, merchant_product_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_prodotti_source "
        "ON prodotti(source, advertiser_id, awin_feed_id)"
    )


def ensure_sync_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feed_sync (
            advertiser_id INTEGER NOT NULL,
            feed_id TEXT NOT NULL,
            advertiser_name TEXT,
            source_updated_at TEXT,
            synced_at TEXT NOT NULL,
            product_count INTEGER NOT NULL,
            status TEXT NOT NULL,
            PRIMARY KEY (advertiser_id, feed_id)
        )
        """
    )
