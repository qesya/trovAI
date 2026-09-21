"""Health check locale/produzione. Non mostra i valori delle credenziali."""

from __future__ import annotations

import json
import os
from pathlib import Path

from src.health import check_database, check_public_configuration


def main():
    base_dir = Path(__file__).resolve().parent
    configured_path = os.getenv("DATABASE_PATH", "shop_database.db")
    database = Path(configured_path)
    if not database.is_absolute():
        database = base_dir / database

    result = {
        **check_database(database),
        **check_public_configuration(),
    }
    result["ready"] = all(
        result[key]
        for key in (
            "database_exists",
            "database_integrity",
            "schema_compatible",
            "gemini_key_configured",
            "site_owner_configured",
            "contact_email_configured",
            "privacy_email_configured",
        )
    ) and int(result["active_products"]) > 0
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["ready"] else 1)


if __name__ == "__main__":
    main()
