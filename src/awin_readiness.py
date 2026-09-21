"""Audit locale dei prerequisiti per candidatura e lancio Awin."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Dict
from urllib.parse import urlparse

from src.health import check_database


REQUIRED_PAGES = {
    "1_Come_funziona.py",
    "2_Trasparenza_affiliazioni.py",
    "3_Privacy.py",
    "4_Termini.py",
    "5_Contatti.py",
}
UNSAFE_CLAIMS = {"partner ufficiale", "feed reale"}


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _valid_public_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _catalog_sources(database: Path) -> Dict[str, int]:
    result = {"demo_products": 0, "awin_products": 0, "awin_products_with_link": 0}
    if not database.is_file():
        return result
    try:
        conn = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
        with conn:
            for source, count in conn.execute(
                "SELECT source, COUNT(*) FROM prodotti "
                "WHERE availability = 1 GROUP BY source"
            ):
                if source == "demo":
                    result["demo_products"] = count
                elif source == "awin":
                    result["awin_products"] = count
            result["awin_products_with_link"] = conn.execute(
                "SELECT COUNT(*) FROM prodotti WHERE source = 'awin' "
                "AND availability = 1 AND aw_deep_link IS NOT NULL "
                "AND TRIM(aw_deep_link) <> ''"
            ).fetchone()[0]
    except sqlite3.Error:
        return result
    finally:
        if "conn" in locals():
            conn.close()
    return result


def _unsafe_claims(project_root: Path) -> bool:
    paths = [project_root / "awin_app5.py", *(project_root / "pages").glob("*.py")]
    combined = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore").lower()
        for path in paths
        if path.is_file()
    )
    return any(claim in combined for claim in UNSAFE_CLAIMS)


def audit(project_root: Path, database: Path) -> Dict[str, object]:
    database_health = check_database(database)
    pages_present = REQUIRED_PAGES <= {
        path.name for path in (project_root / "pages").glob("*.py")
    }
    public_identity = all(
        bool(os.getenv(name))
        for name in ("SITE_OWNER", "CONTACT_EMAIL", "PRIVACY_EMAIL")
    )
    public_url_configured = _valid_public_url(os.getenv("PUBLIC_SITE_URL", ""))
    sources = _catalog_sources(database)
    unsafe_claims_found = _unsafe_claims(project_root)
    content_rights_confirmed = _enabled("CONTENT_RIGHTS_CONFIRMED")
    publisher_id_configured = os.getenv("AWIN_PUBLISHER_ID", "").isdigit()
    tracking_test_confirmed = _enabled("TRACKING_TEST_CONFIRMED")

    common_ready = all(
        (
            database_health["database_integrity"],
            database_health["schema_compatible"],
            int(database_health["active_products"]) > 0,
            pages_present,
            public_identity,
            public_url_configured,
            content_rights_confirmed,
            not unsafe_claims_found,
        )
    )
    network_application_ready = common_ready
    merchant_application_ready = common_ready and publisher_id_configured
    merchant_launch_ready = all(
        (
            merchant_application_ready,
            sources["awin_products"] > 0,
            sources["awin_products_with_link"] == sources["awin_products"],
            sources["demo_products"] == 0,
            tracking_test_confirmed,
        )
    )

    return {
        "database_integrity": database_health["database_integrity"],
        "schema_compatible": database_health["schema_compatible"],
        "active_products": database_health["active_products"],
        "required_pages_present": pages_present,
        "public_identity_configured": public_identity,
        "public_https_url_configured": public_url_configured,
        "content_rights_confirmed": content_rights_confirmed,
        "unsafe_claims_found": unsafe_claims_found,
        "publisher_id_configured": publisher_id_configured,
        "tracking_test_confirmed": tracking_test_confirmed,
        **sources,
        "network_application_ready": network_application_ready,
        "merchant_application_ready": merchant_application_ready,
        "merchant_launch_ready": merchant_launch_ready,
    }
