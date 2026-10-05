"""Test di accettazione dell'aggiornamento incrementale (PostgreSQL reale, Gemini finto).

Si attivano con TROVAI_TEST_DATABASE_URL. Il client Gemini e' sostituito da un
finto che conta le chiamate e i prodotti ricevuti.
"""

from __future__ import annotations

import gzip

import pytest
from conftest import query

from trovai_pipeline import awin_sync, incremental
from trovai_pipeline.database import connect_database
from trovai_pipeline.gemini import RateLimiter

pytestmark = pytest.mark.postgres

AI_FIELDS = {
    "brand": "marca ai", "gender": "uomo", "age_group": "adulto", "color": "nero",
    "material": "cotone", "size": "m", "model_match_confidence": "low",
}


class FakeGemini:
    """Sostituto di enrich_with_gemini: registra chiamate e hash ricevuti."""

    def __init__(self, fail_calls: set[int] | None = None):
        self.calls = 0
        self.hashes: list[str] = []
        self.fail_calls = fail_calls or set()

    def __call__(self, batch, api_key, model):
        self.calls += 1
        if self.calls in self.fail_calls:
            raise ValueError("risposta non valida")
        self.hashes.extend(product.content_hash for product in batch)
        return {product.content_hash: dict(AI_FIELDS) for product in batch}


@pytest.fixture
def run(database, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chiave-di-test")

    def sync(gemini: FakeGemini, **options):
        return awin_sync.sync(apply=True, ai_limit=options.pop("ai_limit", 1000), enrich=gemini,
                              limiter=RateLimiter(0, sleep=lambda _: None), **options)

    return sync


def catalog(make_row, count=3, **overrides):
    return [
        make_row(id=f"p-{index}", title=f"Camicia modello {index}", price="50.00", **overrides)
        for index in range(count)
    ]


def offers(settings):
    return {row[0]: row[1:] for row in query(settings, "SELECT source_product_id, availability, price, ean FROM merchant_offers")}


def test_reimport_same_catalog_makes_zero_ai_calls(run, feed, make_row, database):
    feed(catalog(make_row))
    first = FakeGemini()
    stats = run(first)
    assert (stats["new"], first.calls, stats["ai"]) == (3, 1, 3)

    second = FakeGemini()
    stats = run(second)
    assert second.calls == 0
    assert (stats["new"], stats["unchanged"], stats["updated"], stats["content"]) == (0, 3, 0, 0)
    runs = query(database, "SELECT status, new_count, unchanged_count, ai_count FROM feed_import_runs ORDER BY started_at")
    assert runs == [("success", 3, 0, 3), ("success", 0, 3, 0)]


def test_price_and_size_change_updates_without_ai_and_keeps_enrichment(run, feed, make_row, database):
    feed(catalog(make_row, size="M"))
    run(FakeGemini())
    changed = catalog(make_row, size="L")
    changed[0]["price"] = "39.90"
    feed(changed)
    gemini = FakeGemini()
    stats = run(gemini)
    assert gemini.calls == 0
    assert (stats["updated"], stats["unchanged"]) == (3, 0)
    rows = query(database, "SELECT merchant_product_id, price, size, brand, material FROM catalog_search ORDER BY merchant_product_id")
    assert (rows[0][0], float(rows[0][1]), *rows[0][2:]) == ("p-0", 39.9, "l", "marca ai", "cotone")
    assert {row[2] for row in rows} == {"l"}
    assert {row[3] for row in rows} == {"marca ai"}  # arricchimenti IA conservati


def test_new_products_only_reach_ai(run, feed, make_row):
    feed(catalog(make_row, count=2))
    run(FakeGemini())
    grown = catalog(make_row, count=2) + [make_row(id="nuovo-1", title="Giacca nuova", price="80.00")]
    feed(grown)
    gemini = FakeGemini()
    stats = run(gemini)
    assert (stats["new"], stats["unchanged"]) == (1, 2)
    assert len(gemini.hashes) == 1


def test_sold_out_then_restocked_keeps_ai_data(run, feed, make_row, database):
    feed(catalog(make_row, count=2))
    run(FakeGemini())
    sold_out = catalog(make_row, count=2)
    sold_out[1]["availability"] = "out_of_stock"
    feed(sold_out)
    stats = run(FakeGemini())
    assert stats["deactivated"] == 1
    assert offers(database)["p-1"][0] is False
    assert query(database, "SELECT brand FROM catalog_search WHERE merchant_product_id = 'p-1'") == [("marca ai",)]

    feed(catalog(make_row, count=2))
    gemini = FakeGemini()
    stats = run(gemini)
    assert (stats["reactivated"], gemini.calls) == (1, 0)
    assert query(database, "SELECT availability, brand FROM catalog_search WHERE merchant_product_id = 'p-1'") == [(1, "marca ai")]


def test_partial_download_does_not_deactivate(run, feed, make_row, database):
    feed(catalog(make_row, count=30))
    run(FakeGemini())
    feed(catalog(make_row, count=5))  # il negozio "perde" 25 prodotti su 30: feed sospetto
    stats = run(FakeGemini())
    assert stats["deactivated"] == 0
    assert stats["deactivation_skipped"] == 25
    assert all(available for available, *_ in offers(database).values())
    assert query(database, "SELECT status FROM feed_import_runs ORDER BY started_at DESC LIMIT 1") == [("partial",)]

    # Una rimozione piccola e plausibile invece viene applicata.
    feed(catalog(make_row, count=29))
    stats = run(FakeGemini())
    assert stats["deactivated"] == 1


def test_truncated_feed_fails_without_deactivating(run, feed, make_row, database, tmp_path, monkeypatch):
    feed(catalog(make_row, count=3))
    run(FakeGemini())
    truncated = tmp_path / "troncato.csv.gz"
    truncated.write_bytes(gzip.compress(b"advertiser_id,id,title,price\n" + b"126191,x,Felpa,10\n" * 500)[:-40])
    monkeypatch.setenv("AWIN_FEED_DOWNLOAD_URL", truncated.as_uri())
    with pytest.raises(awin_sync.FeedSyncError):
        run(FakeGemini())
    assert all(available for available, *_ in offers(database).values())
    assert query(database, "SELECT status FROM feed_import_runs ORDER BY started_at DESC LIMIT 1") == [("failed",)]


def test_ai_error_is_recovered_without_reprocessing_completed(run, feed, make_row, monkeypatch):
    monkeypatch.setattr(awin_sync, "AI_BATCH_SIZE", 2)
    feed(catalog(make_row, count=4))
    failing = FakeGemini(fail_calls={1})  # il primo blocco (2 prodotti) fallisce
    stats = run(failing)
    assert (stats["ai"], stats["ai_failed"]) == (2, 2)
    completed = set(failing.hashes)

    retry = FakeGemini()
    stats = run(retry)
    assert stats["ai_retry"] == 2
    assert len(retry.hashes) == 2
    assert not completed & set(retry.hashes)  # nessun prodotto gia' completato viene rinviato

    assert run(FakeGemini()).get("ai_retry", 0) == 0


def test_ai_budget_leftovers_are_picked_up_later(run, feed, make_row):
    feed(catalog(make_row, count=3))
    stats = run(FakeGemini(), ai_limit=1)
    assert (stats["ai"], stats["ai_pending"]) == (1, 2)
    gemini = FakeGemini()
    stats = run(gemini)
    assert (stats["ai_retry"], len(gemini.hashes)) == (2, 2)


def test_identity_ean_variants_merchants_and_duplicates(run, feed, make_row, database):
    feed([
        make_row(id="s-42", title="Sneakers Runner 42", size="42", gtin="4006381333931"),
        make_row(id="s-43", title="Sneakers Runner 43", size="43", gtin="4006381333948"),
        make_row(id="s-43-bis", title="Sneakers Runner 43", size="43", gtin="4006381333948"),  # riga tecnica doppia
        make_row(advertiser_id="777", advertiser_name="Altro", id="o-42", title="Sneakers Runner 42", size="42", gtin="4006381333931"),
        make_row(id="senza-ean", title="Borsa a tracolla"),
    ])
    stats = run(FakeGemini())
    assert stats["duplicates"] == 1
    assert query(database, "SELECT COUNT(*) FROM merchant_offers") == [(4,)]
    # Taglie diverse = varianti distinte; stesso EAN su due negozi = una variante, due offerte.
    assert query(database, "SELECT COUNT(*) FROM product_variants WHERE ean IS NOT NULL") == [(2,)]
    assert query(database, "SELECT COUNT(DISTINCT variant_id) FROM merchant_offers WHERE ean = '4006381333931'") == [(1,)]

    # Reimportazione: nessun duplicato. La borsa riceve l'EAN in seguito: stessa offerta, stessa variante.
    rows = [
        make_row(id="s-42", title="Sneakers Runner 42", size="42", gtin="4006381333931"),
        make_row(id="s-43", title="Sneakers Runner 43", size="43", gtin="4006381333948"),
        make_row(advertiser_id="777", advertiser_name="Altro", id="o-42", title="Sneakers Runner 42", size="42", gtin="4006381333931"),
        make_row(id="senza-ean", title="Borsa a tracolla", gtin="4006381333955"),
    ]
    feed(rows)
    variants_before = query(database, "SELECT COUNT(*) FROM product_variants")
    gemini = FakeGemini()
    stats = run(gemini)
    assert gemini.calls == 0
    assert stats["new"] == 0
    assert query(database, "SELECT COUNT(*) FROM merchant_offers") == [(4,)]
    assert query(database, "SELECT COUNT(*) FROM product_variants") == variants_before
    assert offers(database)["senza-ean"][2] == "4006381333955"
    assert query(database, "SELECT COUNT(*) FROM prodotti") == [(4,)]


def test_concurrent_imports_are_blocked(run, feed, make_row, database):
    feed(catalog(make_row, count=1))
    with connect_database(database) as other:
        assert incremental.try_sync_lock(other)
        with pytest.raises(awin_sync.FeedSyncError, match="in corso"):
            run(FakeGemini())
        incremental.release_sync_lock(other)
    run(FakeGemini())  # dopo il rilascio l'importazione riparte


def test_ai_jobs_are_claimed_only_once(database):
    with connect_database(database) as first, connect_database(database) as second:
        incremental.ensure_ai_jobs_table(first)
        first.commit()
        assert incremental.claim_ai_jobs(first, ["h1", "h2"], "run-a", "modello") == {"h1", "h2"}
        first.commit()
        assert incremental.claim_ai_jobs(second, ["h1", "h2", "h3"], "run-b", "modello") == {"h3"}
        second.commit()  # la presa in carico va confermata subito, come fa apply_enrichment
        incremental.finish_ai_jobs(first, done=["h1"], failed=["h2"], error="boom")
        first.commit()
        assert incremental.claim_ai_jobs(second, ["h1", "h2"], "run-b", "modello") == {"h2"}
