"""Import completo su PostgreSQL reale, con un feed finto su file e senza Gemini.

Si attiva solo con TROVAI_TEST_DATABASE_URL (in CI c'e' un Postgres dedicato).
ATTENZIONE: cancella e ricrea lo schema ``public`` del database indicato.
"""

from __future__ import annotations

import csv

import pytest

from trovai_pipeline import awin_sync, pipeline, title_review
from trovai_pipeline.database import connect_database

pytestmark = pytest.mark.postgres

@pytest.fixture
def database(postgres_settings, monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", postgres_settings.host)
    monkeypatch.setenv("POSTGRES_PORT", str(postgres_settings.port))
    monkeypatch.setenv("POSTGRES_DATABASE", postgres_settings.database)
    monkeypatch.setenv("POSTGRES_USER", postgres_settings.user)
    monkeypatch.setenv("POSTGRES_PASSWORD", postgres_settings.password or "test")
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


def jordan(make_row, advertiser_id, product_id, price):
    return make_row(advertiser_id=advertiser_id, advertiser_name=f"negozio {advertiser_id}", id=product_id,
                    title="Nike Air Jordan 1 Low Bred Toe - 42", brand="Nike", price=price, gtin="0195866123456")


def query(settings, sql, params=None):
    with connect_database(settings) as conn:
        return conn.execute(sql, params).fetchall()


def test_sync_merges_same_ean_and_tracks_availability(database, feed, make_row):
    feed([
        jordan(make_row, "1", "a-1", "189.90"),
        jordan(make_row, "2", "b-1", "175.00"),
        make_row(advertiser_id="1", id="a-2", title="Felpa con cappuccio Nera - M"),
        make_row(advertiser_id="1", id="a-3", title="Borsa a spalla", availability="out_of_stock"),
        make_row(advertiser_id="1", id="a-4", title="Senza prezzo", price=""),
    ])
    stats = awin_sync.sync(apply=True, ai_limit=0)
    assert (stats["received"], stats["eligible"], stats["removed_unavailable"], stats["skipped_invalid"]) == (5, 3, 1, 1)

    # Stesso EAN su due negozi -> un solo prodotto con due offerte.
    rows = query(database, "SELECT product_id, merchant, price FROM catalog_search WHERE brand = 'nike' ORDER BY price")
    assert len(rows) == 2
    assert rows[0][0] == rows[1][0]
    assert [float(row[2]) for row in rows] == [175.0, 189.9]

    felpa = query(database, "SELECT title, color, size FROM catalog_search WHERE merchant_product_id = 'a-2'")
    assert felpa == [("Felpa con cappuccio", "nero", "m")]

    # Run successivo: l'offerta sparita dal feed diventa non disponibile.
    feed([jordan(make_row, "1", "a-1", "179.90"), jordan(make_row, "2", "b-1", "175.00")])
    awin_sync.sync(apply=True, ai_limit=0)
    availability = dict(query(database, "SELECT source_product_id, availability FROM merchant_offers"))
    assert availability == {"a-1": True, "b-1": True, "a-2": False}
    assert query(database, "SELECT COUNT(*) FROM prodotti WHERE source = 'awin'") == [(2,)]
    assert float(query(database, "SELECT price FROM merchant_offers WHERE source_product_id = 'a-1'")[0][0]) == pytest.approx(179.9)
    runs = query(database, "SELECT status, imported_count FROM feed_import_runs ORDER BY started_at")
    assert [run[0] for run in runs] == ["success", "success"]


def test_bootstrap_export_and_downstream_schemas(database, feed, make_row, tmp_path):
    feed([
        jordan(make_row, "1", "a-1", "189.90"),
        make_row(advertiser_id="2", id="b-9", title="Cappello taglia unica Nero", size="One Size"),
    ])
    export = tmp_path / "catalogo.csv"
    stats = awin_sync.bootstrap_clean_catalog(limit=10, ai_limit=0, export_csv=export, replace_catalog=True)
    assert stats["selected"] == 2

    with export.open(encoding="utf-8") as handle:
        exported = {row["source_product_id"]: row for row in csv.DictReader(handle)}
    assert exported["b-9"]["size"] == "taglia unica"
    assert exported["b-9"]["title"] == "Cappello"

    assert awin_sync.refresh_display_titles() == 2
    titles = {row[0] for row in query(database, "SELECT canonical_title FROM catalog_products")}
    assert titles == {"Air Jordan 1 Low Bred Toe nike", "Cappello"}

    # Le fasi successive creano le proprie tabelle e viste senza errori.
    with connect_database(database) as conn:
        pipeline.ensure_future_visual_schema(conn)
        title_review.ensure_review_schema(conn)
    assert query(database, "SELECT COUNT(*) FROM catalog_search_enriched") == [(2,)]

    preview = title_review.run_review(apply=False, limit=1)
    assert (preview["scanned"], preview["queued"]) == (2, 1)


def test_prodotti_table_is_created_and_upgraded(database):
    from trovai_pipeline.schema import PRODOTTI_COLUMNS, ensure_prodotti_table

    with connect_database(database) as conn:
        # Simula un database vecchio, creato dall'app con meno colonne.
        conn.execute("CREATE TABLE prodotti (id BIGSERIAL PRIMARY KEY, sku TEXT NOT NULL UNIQUE, title TEXT)")
        conn.execute("INSERT INTO prodotti (sku, title) VALUES ('1:x', 'vecchio')")
        ensure_prodotti_table(conn)
        ensure_prodotti_table(conn)  # idempotente
    columns = {row[0] for row in query(database, "SELECT column_name FROM information_schema.columns WHERE table_name = 'prodotti'")}
    assert {column[0] for column in PRODOTTI_COLUMNS} | {"id", "sku"} == columns
    assert query(database, "SELECT title FROM prodotti") == [("vecchio",)]


def test_new_prodotti_table_enforces_original_constraints(database):
    import psycopg

    from trovai_pipeline.schema import ensure_prodotti_table

    with connect_database(database) as conn:
        ensure_prodotti_table(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        with connect_database(database) as conn:
            conn.execute("INSERT INTO prodotti (sku, title, price, availability, merchant) VALUES ('1:a', 't', -1, 1, 'm')")
    with pytest.raises(psycopg.errors.NotNullViolation):
        with connect_database(database) as conn:
            conn.execute("INSERT INTO prodotti (sku, price, availability, merchant) VALUES ('1:b', 1, 1, 'm')")
    with connect_database(database) as conn:
        conn.execute("INSERT INTO prodotti (sku, title, price, availability, merchant) VALUES ('1:c', 't', 1, 1, 'm')")
    assert query(database, "SELECT currency, source FROM prodotti") == [("EUR", "demo")]


def test_bootstrap_requires_explicit_replace(database, feed, make_row):
    feed([make_row()])
    with pytest.raises(awin_sync.FeedSyncError):
        awin_sync.bootstrap_clean_catalog(limit=1, ai_limit=0, export_csv=None, replace_catalog=False)
