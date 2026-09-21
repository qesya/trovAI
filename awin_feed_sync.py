"""Sincronizza un insieme esplicito di advertiser Awin autorizzati."""

from __future__ import annotations

from pathlib import Path

from src.awin_feed import AwinFeedError, sync_selected_feeds
from src.config import ConfigurationError, database_path, get_setting


def parse_advertiser_ids(raw_value: str):
    try:
        values = [int(value.strip()) for value in raw_value.split(",") if value.strip()]
    except ValueError as exc:
        raise ConfigurationError(
            "AWIN_ADVERTISER_IDS deve contenere ID numerici separati da virgola"
        ) from exc
    if not values:
        raise ConfigurationError(
            "Configura almeno un advertiser autorizzato in AWIN_ADVERTISER_IDS"
        )
    return values


def main():
    base_dir = Path(__file__).resolve().parent
    api_key = get_setting("AWIN_DATAFEED_API_KEY", required=True)
    advertiser_ids = parse_advertiser_ids(
        get_setting("AWIN_ADVERTISER_IDS", required=True) or ""
    )
    database = database_path(
        base_dir, get_setting("DATABASE_PATH", default="shop_database.db")
    )
    try:
        imported = sync_selected_feeds(api_key or "", advertiser_ids, database)
    except AwinFeedError as exc:
        raise SystemExit(str(exc)) from None
    if not imported:
        print("Nessun feed Joined corrisponde agli advertiser configurati.")
        return
    for advertiser_id, total in imported.items():
        print(f"Advertiser {advertiser_id}: {total} prodotti importati o aggiornati")


if __name__ == "__main__":
    main()
