"""Raccolta minimale di feedback sui risultati, senza identificatori utente."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def ensure_feedback_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS product_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            helpful INTEGER NOT NULL CHECK (helpful IN (0, 1)),
            created_at TEXT NOT NULL
        )
        """
    )


def record_product_feedback(database_path: str, product_id: int, helpful: bool) -> None:
    with sqlite3.connect(database_path) as conn:
        ensure_feedback_table(conn)
        conn.execute(
            "INSERT INTO product_feedback (product_id, helpful, created_at) "
            "VALUES (?, ?, ?)",
            (int(product_id), int(helpful), datetime.now(timezone.utc).isoformat()),
        )
