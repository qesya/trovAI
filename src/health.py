"""Controlli di readiness che non stampano mai il valore dei segreti."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Dict


REQUIRED_PRODUCT_COLUMNS = {
    "id",
    "title",
    "price",
    "availability",
    "merchant",
    "merchant_deep_link",
    "source",
}


def check_database(database: Path) -> Dict[str, object]:
    result: Dict[str, object] = {
        "database_exists": database.is_file(),
        "database_integrity": False,
        "schema_compatible": False,
        "active_products": 0,
    }
    if not database.is_file():
        return result
    try:
        conn = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
        with conn:
            result["database_integrity"] = (
                conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            )
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(prodotti)").fetchall()
            }
            result["schema_compatible"] = REQUIRED_PRODUCT_COLUMNS <= columns
            if result["schema_compatible"]:
                result["active_products"] = conn.execute(
                    "SELECT COUNT(*) FROM prodotti WHERE availability = 1"
                ).fetchone()[0]
    except sqlite3.Error:
        return result
    finally:
        if "conn" in locals():
            conn.close()
    return result


def check_public_configuration() -> Dict[str, bool]:
    return {
        "gemini_key_configured": bool(os.getenv("GEMINI_API_KEY")),
        "site_owner_configured": bool(os.getenv("SITE_OWNER")),
        "contact_email_configured": bool(os.getenv("CONTACT_EMAIL")),
        "privacy_email_configured": bool(os.getenv("PRIVACY_EMAIL")),
    }
