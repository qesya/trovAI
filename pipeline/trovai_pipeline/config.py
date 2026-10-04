"""Configurazione locale e CI: secrets.toml opzionale + variabili d'ambiente.

Ordine di priorita' (dal piu' forte):
1. variabili d'ambiente (GitHub Actions, server, shell);
2. ``.streamlit/secrets.toml`` nella cartella del progetto, se esiste.

La cartella del progetto e' ``TROVAI_HOME`` se impostata, altrimenti la
cartella da cui si lancia il comando. I valori non vengono mai stampati.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

# Tutte le chiavi lette dal progetto. Solo queste vengono prese dall'ambiente,
# cosi' nessuna variabile estranea del sistema finisce nella configurazione.
KNOWN_KEYS = (
    "AWIN_FEED_DOWNLOAD_URL",
    "GEMINI_API_KEY",
    "GEMINI_FEED_API_KEY",
    "GEMINI_EMBEDDING_API_KEY",
    "GEMINI_VISION_API_KEY",
    "FEED_ENRICHMENT_MODEL",
    "TITLE_REVIEW_MODEL",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DATABASE",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
)


def project_root() -> Path:
    return Path(os.environ.get("TROVAI_HOME") or Path.cwd()).resolve()


def secrets_path() -> Path:
    override = os.environ.get("TROVAI_SECRETS_FILE")
    return Path(override).expanduser() if override else project_root() / ".streamlit" / "secrets.toml"


def load_secrets() -> dict[str, Any]:
    """Unisce secrets.toml (se presente) e variabili d'ambiente."""
    values: dict[str, Any] = {}
    path = secrets_path()
    if path.is_file():
        with path.open("rb") as handle:
            values.update(tomllib.load(handle))
    for key in KNOWN_KEYS:
        env_value = os.environ.get(key)
        if env_value is not None and env_value.strip():
            values[key] = env_value.strip()
    return values
