from __future__ import annotations

import csv
import gzip
import io
import sqlite3

import pytest

from trovai_pipeline import awin_sync
from trovai_pipeline.awin_sync import apply_enrichment, detect_encoding, download_rows, select_balanced_products
from trovai_pipeline.feed_cleaner import clean_row
from trovai_pipeline.gemini import RateLimiter
from trovai_pipeline.title_review import title_issues


def write_feed(path, rows, *, encoding="utf-8", compress=False):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    data = buffer.getvalue().encode(encoding)
    path.write_bytes(gzip.compress(data) if compress else data)
    return path.as_uri()


# --- Lettura del feed ------------------------------------------------------------------

def test_detect_encoding():
    assert detect_encoding(b"\xef\xbb\xbfid,title") == "utf-8-sig"
    assert detect_encoding("Maglia però".encode("utf-8")) == "utf-8"
    assert detect_encoding("Maglia però".encode("cp1252")) == "cp1252"


@pytest.mark.parametrize("encoding, compress", [("utf-8", False), ("utf-8", True), ("cp1252", True)])
def test_download_rows_reads_plain_gzip_and_cp1252(tmp_path, make_row, encoding, compress):
    url = write_feed(tmp_path / "feed.csv", [make_row(title="Maglia però")], encoding=encoding, compress=compress)
    with download_rows(url) as rows:
        parsed = list(rows)
    assert [row["title"] for row in parsed] == ["Maglia però"]


def test_download_rows_wraps_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(awin_sync.time, "sleep", lambda _: None)
    with pytest.raises(awin_sync.FeedSyncError):
        with download_rows((tmp_path / "manca.csv").as_uri()):
            pass


# --- Campione bilanciato ---------------------------------------------------------------

def test_select_balanced_products_prefers_distinct_models(make_row):
    products = [clean_row(make_row(advertiser_id="1", id=f"a{size}", title=f"Sneaker Alpha - {size}")) for size in (40, 41, 42)]
    products += [clean_row(make_row(advertiser_id="1", id="b", title="Sneaker Beta"))]
    products += [clean_row(make_row(advertiser_id="2", id="c", title="Borsa Gamma"))]
    selected = select_balanced_products(products, 3)
    assert {product.source_product_id for product in selected} == {"a40", "b", "c"}


# --- Arricchimento Gemini ----------------------------------------------------------------

@pytest.fixture
def cache_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE feed_enrichment_cache (content_hash TEXT PRIMARY KEY, metadata_json TEXT NOT NULL, enriched_at TEXT NOT NULL)")
    yield conn
    conn.close()


def no_wait_limiter():
    return RateLimiter(0, sleep=lambda _: None)


def products_for_enrichment(make_row, count):
    return [clean_row(make_row(id=str(index), title=f"Felpa modello {index}")) for index in range(count)]


def test_apply_enrichment_retries_quota_errors(cache_conn, make_row, monkeypatch):
    monkeypatch.setattr("trovai_pipeline.gemini.time.sleep", lambda _: None)
    products = products_for_enrichment(make_row, 3)
    calls = {"n": 0}

    def fake_enrich(batch, key, model):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("429 RESOURCE_EXHAUSTED retry in 0s")
        return {product.content_hash: {"color": "black"} for product in batch}

    result = apply_enrichment(cache_conn, products, "chiave", "modello", 10, review_all=True,
                              force_fresh=True, limiter=no_wait_limiter(), enrich=fake_enrich)
    assert (result.enriched, result.failed) == (3, 0)
    assert all(product.color == "nero" for product in products)
    assert cache_conn.execute("SELECT COUNT(*) FROM feed_enrichment_cache").fetchone()[0] == 3


def test_apply_enrichment_counts_failures_instead_of_hiding_them(cache_conn, make_row, monkeypatch):
    monkeypatch.setattr(awin_sync, "AI_BATCH_SIZE", 2)
    products = products_for_enrichment(make_row, 4)

    def fake_enrich(batch, key, model):
        if batch[0] is products[0]:
            raise ValueError("JSON non valido")
        return {batch[0].content_hash: {"color": "white"}}  # il secondo prodotto manca nella risposta

    result = apply_enrichment(cache_conn, products, "chiave", "modello", 10, review_all=True,
                              force_fresh=True, limiter=no_wait_limiter(), enrich=fake_enrich)
    assert (result.enriched, result.failed) == (1, 3)
    assert products[2].color == "bianco"


def test_apply_enrichment_uses_cache_and_budget(cache_conn, make_row):
    products = products_for_enrichment(make_row, 3)
    seen: list[str] = []

    def fake_enrich(batch, key, model):
        seen.extend(product.content_hash for product in batch)
        return {product.content_hash: {"color": "red"} for product in batch}

    first = apply_enrichment(cache_conn, products, "chiave", "modello", 2, review_all=True,
                             limiter=no_wait_limiter(), enrich=fake_enrich)
    assert first.enriched == 2                  # rispetta il budget
    seen.clear()
    fresh_products = products_for_enrichment(make_row, 3)
    second = apply_enrichment(cache_conn, fresh_products, "chiave", "modello", 10, review_all=True,
                              limiter=no_wait_limiter(), enrich=fake_enrich)
    assert second.enriched == 1                 # solo quello non in cache
    assert len(seen) == 1
    assert all(product.color == "rosso" for product in fresh_products)


def test_apply_enrichment_without_key_does_nothing(cache_conn, make_row):
    def must_not_be_called(*_):
        raise AssertionError("Gemini chiamato senza chiave")

    result = apply_enrichment(cache_conn, products_for_enrichment(make_row, 2), None, "modello", 10,
                              review_all=True, enrich=must_not_be_called)
    assert (result.enriched, result.failed) == (0, 0)


# --- Validazione titoli ----------------------------------------------------------------

@pytest.mark.parametrize("title, issues", [
    ("Dunk High", []),
    ("", ["titolo_vuoto"]),
    ("Energy sneakers in", ["connettivo_finale", "preposizione_finale"]),
    ("Polo nera", ["attributo_nel_titolo"]),  # forme femminili/plurali dei colori
    ("Sneakers bianche", ["attributo_nel_titolo"]),
    ("Polo black", ["attributo_nel_titolo"]),
])
def test_title_issues(title, issues):
    assert title_issues(title, brand=None, color=None, material=None, gender=None, age_group=None) == issues
