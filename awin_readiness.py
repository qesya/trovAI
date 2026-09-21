"""Stampa lo stato dei gate Awin senza mostrare credenziali o dati societari."""

from __future__ import annotations

import json
import os
from pathlib import Path

from src.awin_readiness import audit


def main():
    project_root = Path(__file__).resolve().parent
    database = Path(os.getenv("DATABASE_PATH", "shop_database.db"))
    if not database.is_absolute():
        database = project_root / database
    result = audit(project_root, database)
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["merchant_launch_ready"] else 1)


if __name__ == "__main__":
    main()
