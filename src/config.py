"""Configurazione dell'applicazione, senza segreti inclusi nel codice."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Optional


class ConfigurationError(RuntimeError):
    """Indica che una configurazione obbligatoria non e disponibile."""


def get_setting(
    name: str,
    secrets: Optional[Mapping[str, Any]] = None,
    *,
    required: bool = False,
    default: Optional[str] = None,
) -> Optional[str]:
    """Legge una configurazione dall'ambiente o, in seconda battuta, dai secrets."""
    value = os.getenv(name)
    if not value and secrets is not None:
        try:
            secret_value = secrets.get(name)
        except Exception:
            secret_value = None
        if secret_value is not None:
            value = str(secret_value)

    value = value or default
    if required and not value:
        raise ConfigurationError(
            f"Configurazione obbligatoria mancante: {name}. "
            "Impostala come variabile d'ambiente o in .streamlit/secrets.toml."
        )
    return value


def database_path(base_dir: Path, configured_path: Optional[str] = None) -> Path:
    """Restituisce un percorso assoluto per il database dell'app."""
    if configured_path:
        candidate = Path(configured_path).expanduser()
        return candidate if candidate.is_absolute() else base_dir / candidate
    return base_dir / "shop_database.db"
