"""Download, normalizzazione e importazione dei product feed Awin."""

from __future__ import annotations

import csv
import gzip
import io
import sqlite3
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from src.catalog_schema import ensure_awin_columns, ensure_sync_table


FEED_LIST_ENDPOINT = "https://productdata.awin.com/datafeed/list/apikey/{api_key}"


class AwinFeedError(RuntimeError):
    """Errore di sincronizzazione che non include URL contenenti credenziali."""


@dataclass(frozen=True)
class FeedReference:
    advertiser_id: int
    advertiser_name: str
    feed_id: str
    feed_name: str
    membership_status: str
    last_imported: Optional[str]
    url: str


def _canonical_key(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def _value(row: Mapping[str, str], *names: str) -> Optional[str]:
    canonical = {_canonical_key(key): value for key, value in row.items()}
    for name in names:
        value = canonical.get(_canonical_key(name))
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def parse_csv_bytes(payload: bytes) -> List[Dict[str, str]]:
    if payload[:2] == b"\x1f\x8b":
        payload = gzip.decompress(payload)
    text = payload.decode("utf-8-sig", errors="replace")
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [dict(row) for row in csv.DictReader(io.StringIO(text), dialect=dialect)]


def download_bytes(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "TrovAI-Awin-Feed-Sync/1.0", "Accept-Encoding": "gzip"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        raise AwinFeedError("Impossibile scaricare i dati dal product feed Awin") from None


def fetch_feed_references(api_key: str) -> List[FeedReference]:
    encoded_key = urllib.parse.quote(api_key, safe="")
    rows = parse_csv_bytes(
        download_bytes(FEED_LIST_ENDPOINT.format(api_key=encoded_key))
    )
    references = []
    for row in rows:
        advertiser_id = _value(row, "Advertiser ID", "Merchant ID")
        url = _value(row, "URL")
        if not advertiser_id or not url:
            continue
        references.append(
            FeedReference(
                advertiser_id=int(advertiser_id),
                advertiser_name=_value(row, "Advertiser Name", "Merchant Name") or "",
                feed_id=_value(row, "Feed ID") or "default",
                feed_name=_value(row, "Feed Name") or "Default",
                membership_status=_value(row, "Membership Status") or "",
                last_imported=_value(row, "Last Imported"),
                url=url,
            )
        )
    return references


def _as_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    normalized = value.strip().replace(" ", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def _availability(row: Mapping[str, str]) -> int:
    raw = (_value(row, "in_stock", "stock_status", "availability") or "").lower()
    unavailable = {"0", "false", "no", "out of stock", "out_of_stock", "unavailable"}
    return int(raw not in unavailable)


def normalize_product(
    row: Mapping[str, str], advertiser_id: int, advertiser_name: str
) -> Optional[Dict[str, object]]:
    merchant_product_id = _value(
        row, "merchant_product_id", "aw_product_id", "product_id", "id"
    )
    title = _value(row, "product_name", "title", "name")
    if not merchant_product_id or not title:
        return None

    current_price = _as_float(
        _value(row, "search_price", "store_price", "product_price", "price")
    )
    old_price = _as_float(_value(row, "rrp_price", "product_price_old"))
    if current_price is None:
        return None
    if old_price is not None and old_price > current_price:
        price, sale_price = old_price, current_price
    else:
        price, sale_price = current_price, None

    return {
        "sku": f"{advertiser_id}:{merchant_product_id}",
        "title": title,
        "description": _value(
            row, "description", "product_short_description", "product_description"
        ),
        "brand": _value(row, "brand_name", "brand"),
        "product_type": _value(row, "product_type", "category_name"),
        "sottocategoria": _value(
            row, "merchant_product_category_path", "merchant_category"
        ),
        "gender": _value(row, "gender"),
        "age_group": _value(row, "age_group"),
        "color": _value(row, "colour", "color"),
        "size": _value(row, "size"),
        "material": _value(row, "material"),
        "price": price,
        "sale_price": sale_price,
        "availability": _availability(row),
        "condizione": _value(row, "condition") or "Nuovo",
        "merchant": _value(row, "merchant_name", "advertiser_name")
        or advertiser_name,
        "image_link": _value(
            row, "aw_image_url", "merchant_image_url", "large_image", "image_link"
        ),
        "merchant_deep_link": _value(row, "merchant_deep_link", "product_url"),
        "advertiser_id": advertiser_id,
        "merchant_product_id": merchant_product_id,
        "aw_deep_link": _value(row, "aw_deep_link"),
        "currency": _value(row, "currency") or "EUR",
        "source": "awin",
        "source_updated_at": _value(row, "last_updated", "last_imported"),
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }


def import_feed_rows(
    conn: sqlite3.Connection,
    rows: Iterable[Mapping[str, str]],
    reference: FeedReference,
) -> int:
    ensure_awin_columns(conn)
    ensure_sync_table(conn)
    products = [
        product
        for row in rows
        if (product := normalize_product(row, reference.advertiser_id, reference.advertiser_name))
        is not None
    ]
    if not products:
        return 0

    for product in products:
        product["awin_feed_id"] = reference.feed_id
        if not product["source_updated_at"]:
            product["source_updated_at"] = reference.last_imported

    conn.execute(
        """
        UPDATE prodotti SET availability = 0
        WHERE source = 'awin' AND advertiser_id = ? AND awin_feed_id = ?
        """,
        (reference.advertiser_id, reference.feed_id),
    )

    columns = list(products[0])
    column_names = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    updates = ", ".join(
        f"{column}=excluded.{column}"
        for column in columns
        if column not in {"advertiser_id", "merchant_product_id"}
    )
    conn.executemany(
        f"""
        INSERT INTO prodotti ({column_names}) VALUES ({placeholders})
        ON CONFLICT(advertiser_id, merchant_product_id)
        DO UPDATE SET {updates}
        """,
        ([product[column] for column in columns] for product in products),
    )
    conn.execute(
        """
        INSERT INTO feed_sync (
            advertiser_id, feed_id, advertiser_name, source_updated_at,
            synced_at, product_count, status
        ) VALUES (?, ?, ?, ?, ?, ?, 'success')
        ON CONFLICT(advertiser_id, feed_id) DO UPDATE SET
            advertiser_name=excluded.advertiser_name,
            source_updated_at=excluded.source_updated_at,
            synced_at=excluded.synced_at,
            product_count=excluded.product_count,
            status=excluded.status
        """,
        (
            reference.advertiser_id,
            reference.feed_id,
            reference.advertiser_name,
            reference.last_imported,
            datetime.now(timezone.utc).isoformat(),
            len(products),
        ),
    )
    return len(products)


def sync_selected_feeds(
    api_key: str, advertiser_ids: Sequence[int], database: Path
) -> Dict[int, int]:
    allowlist = set(advertiser_ids)
    references = [
        reference
        for reference in fetch_feed_references(api_key)
        if reference.advertiser_id in allowlist
        and reference.membership_status.strip().lower() == "joined"
    ]
    imported = {}
    with sqlite3.connect(database) as conn:
        for reference in references:
            rows = parse_csv_bytes(download_bytes(reference.url))
            imported[reference.advertiser_id] = imported.get(reference.advertiser_id, 0)
            imported[reference.advertiser_id] += import_feed_rows(conn, rows, reference)
    return imported
