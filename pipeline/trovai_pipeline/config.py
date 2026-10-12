"""Configurazione locale e CI: file ``.env`` opzionale + variabili d'ambiente.

Ordine di priorita' (dal piu' forte):
1. variabili d'ambiente (GitHub Actions, server, shell);
2. ``.env`` nella cartella del progetto (o ``TROVAI_ENV_FILE``), se esiste;
3. ``.streamlit/secrets.toml`` (o ``TROVAI_SECRETS_FILE``): formato storico,
   ancora letto per compatibilita' con le installazioni esistenti.

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
    "DATABASE_URL",
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


def env_file_path() -> Path:
    override = os.environ.get("TROVAI_ENV_FILE")
    return Path(override).expanduser() if override else project_root() / ".env"


def parse_env_file(text: str) -> dict[str, str]:
    """Legge righe ``CHIAVE=valore`` (commenti, ``export`` e virgolette ammessi)."""
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if key and value:
            values[key] = value
    return values


def load_secrets() -> dict[str, Any]:
    """Unisce secrets.toml storico, ``.env`` e variabili d'ambiente."""
    values: dict[str, Any] = {}
    path = secrets_path()
    if path.is_file():
        with path.open("rb") as handle:
            values.update(tomllib.load(handle))
    env_path = env_file_path()
    if env_path.is_file():
        values.update(parse_env_file(env_path.read_text(encoding="utf-8")))
    for key in KNOWN_KEYS:
        env_value = os.environ.get(key)
        if env_value is not None and env_value.strip():
            values[key] = env_value.strip()
    return values
