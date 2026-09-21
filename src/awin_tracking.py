"""Client e cache per il Link Builder API di Awin."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Mapping, Optional


API_BASE_URL = "https://api.awin.com"


class AwinTrackingError(RuntimeError):
    """Errore controllato del Link Builder, privo di credenziali nel messaggio."""


def build_click_parameters(product_id: int, position: int, campaign: str) -> Dict[str, str]:
    """Crea riferimenti analitici che non contengono dati utente o testo della chat."""
    return {
        "campaign": campaign[:50],
        "clickref": "trovai-search",
        "clickref2": f"product-{int(product_id)}",
        "clickref3": f"position-{int(position)}",
    }


class AwinLinkBuilderClient:
    def __init__(
        self,
        publisher_id: int,
        api_token: str,
        opener: Callable = urllib.request.urlopen,
        timeout: int = 10,
    ):
        self.publisher_id = int(publisher_id)
        self._api_token = api_token
        self._opener = opener
        self.timeout = timeout

    def generate(
        self,
        advertiser_id: int,
        destination_url: str,
        parameters: Mapping[str, str],
    ) -> str:
        endpoint = (
            f"{API_BASE_URL}/publishers/{self.publisher_id}/linkbuilder/generate"
        )
        payload = json.dumps(
            {
                "advertiserId": int(advertiser_id),
                "destinationUrl": destination_url,
                "parameters": dict(parameters),
                "shorten": False,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "TrovAI-Awin-Link-Builder/1.0",
            },
        )
        try:
            with self._opener(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            raise AwinTrackingError("Link Builder Awin non disponibile") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AwinTrackingError("Risposta non valida dal Link Builder Awin") from exc

        url = result.get("url") if isinstance(result, dict) else None
        if not url:
            raise AwinTrackingError("Awin non ha generato un tracking link")
        return str(url)


class TrackingLinkCache:
    def __init__(self, conn: sqlite3.Connection, ttl_days: int = 7):
        self.conn = conn
        self.ttl = timedelta(days=ttl_days)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tracking_links (
                cache_key TEXT PRIMARY KEY,
                advertiser_id INTEGER NOT NULL,
                destination_url TEXT NOT NULL,
                tracking_url TEXT NOT NULL,
                parameters_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

    @staticmethod
    def cache_key(
        advertiser_id: int, destination_url: str, parameters: Mapping[str, str]
    ) -> str:
        canonical = json.dumps(
            [int(advertiser_id), destination_url, dict(sorted(parameters.items()))],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def get(
        self, advertiser_id: int, destination_url: str, parameters: Mapping[str, str]
    ) -> Optional[str]:
        key = self.cache_key(advertiser_id, destination_url, parameters)
        row = self.conn.execute(
            "SELECT tracking_url, created_at FROM tracking_links WHERE cache_key = ?",
            (key,),
        ).fetchone()
        if not row:
            return None
        try:
            created_at = datetime.fromisoformat(row[1])
        except ValueError:
            return None
        if datetime.now(timezone.utc) - created_at > self.ttl:
            self.conn.execute("DELETE FROM tracking_links WHERE cache_key = ?", (key,))
            return None
        return str(row[0])

    def put(
        self,
        advertiser_id: int,
        destination_url: str,
        parameters: Mapping[str, str],
        tracking_url: str,
    ) -> None:
        key = self.cache_key(advertiser_id, destination_url, parameters)
        self.conn.execute(
            """
            INSERT INTO tracking_links (
                cache_key, advertiser_id, destination_url, tracking_url,
                parameters_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                tracking_url=excluded.tracking_url,
                created_at=excluded.created_at
            """,
            (
                key,
                int(advertiser_id),
                destination_url,
                tracking_url,
                json.dumps(dict(parameters), sort_keys=True),
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def resolve_tracking_url(
    conn: sqlite3.Connection,
    client: AwinLinkBuilderClient,
    advertiser_id: int,
    destination_url: str,
    parameters: Mapping[str, str],
) -> str:
    cache = TrackingLinkCache(conn)
    cached = cache.get(advertiser_id, destination_url, parameters)
    if cached:
        return cached
    tracking_url = client.generate(advertiser_id, destination_url, parameters)
    cache.put(advertiser_id, destination_url, parameters, tracking_url)
    return tracking_url
