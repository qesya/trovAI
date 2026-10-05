from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any

import pytest


def feed_row(**overrides: Any) -> dict[str, str]:
    """Riga minima valida di un feed Awin; i test sovrascrivono solo cio' che serve."""
    row = {
        "advertiser_id": "126191",
        "advertiser_name": "Costumein",
        "id": "58748950937949",
        "title": "Camicia Andrea a righe",
        "price": "59.00",
        "link": "https://merchant.example/p/1",
        "aw_deep_link": "https://www.awin1.com/pclick.php?p=1",
        "image_link": "https://merchant.example/i/1.jpg",
        "availability": "in_stock",
        "currency": "EUR",
    }
    row.update({key: str(value) for key, value in overrides.items()})
    return row


@pytest.fixture
def make_row():
    return feed_row


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, tmp_path):
    """Nessun test deve leggere chiavi reali dall'ambiente o dal disco."""
    from trovai_pipeline import config

    for key in config.KNOWN_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TROVAI_HOME", str(tmp_path))
    monkeypatch.delenv("TROVAI_SECRETS_FILE", raising=False)
    monkeypatch.delenv("TROVAI_ENV_FILE", raising=False)


@pytest.fixture
def postgres_settings():
    """Database PostgreSQL usa-e-getta indicato da TROVAI_TEST_DATABASE_URL."""
    url = os.environ.get("TROVAI_TEST_DATABASE_URL")
    if not url:
        pytest.skip("TROVAI_TEST_DATABASE_URL non impostata")
    from trovai_pipeline.database import database_settings

    return database_settings(Path("."), {"DATABASE_URL": url})


# --- PostgreSQL di test (fixture condivise dai test di integrazione) --------------------

@pytest.fixture
def database(postgres_settings, monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", postgres_settings.host)
    monkeypatch.setenv("POSTGRES_PORT", str(postgres_settings.port))
    monkeypatch.setenv("POSTGRES_DATABASE", postgres_settings.database)
    monkeypatch.setenv("POSTGRES_USER", postgres_settings.user)
    monkeypatch.setenv("POSTGRES_PASSWORD", postgres_settings.password or "test")
    from trovai_pipeline.database import connect_database

    with connect_database(postgres_settings) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")  # database vuoto: la pipeline crea tutto
    return postgres_settings


@pytest.fixture
def feed(tmp_path, monkeypatch, make_row):
    path = tmp_path / "feed.csv"

    def publish(rows):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=sorted({key for row in rows for key in row}))
            writer.writeheader()
            writer.writerows(rows)
        monkeypatch.setenv("AWIN_FEED_DOWNLOAD_URL", path.as_uri())

    return publish



def query(settings, sql, params=None):
    from trovai_pipeline.database import connect_database

    with connect_database(settings) as conn:
        return conn.execute(sql, params).fetchall()
