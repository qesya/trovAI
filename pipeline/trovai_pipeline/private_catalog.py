"""Prepare the catalog for server-only SQL access while keeping Supabase Data API enabled."""
from __future__ import annotations

import argparse

from trovai_pipeline.awin_sync import ensure_schema
from trovai_pipeline.config import load_secrets, project_root
from trovai_pipeline.database import connect_database, database_settings
from trovai_pipeline.normalized_catalog import ensure_normalized_schema

TABLES = (
    'prodotti', 'feed_enrichment_cache', 'feed_import_runs', 'feed_ai_jobs',
    'catalog_products', 'product_color_variants', 'product_variants', 'merchant_offers',
    'product_feedback', 'tracking_links',
)


def prepare_private_catalog(conn) -> None:
    # Current creator only: future views recreated by sync must not inherit API grants.
    api_roles = ['PUBLIC'] + [row[0] for row in conn.execute(
        "SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')"
    ).fetchall()]
    for role in api_roles:
        for kind in ('TABLES', 'SEQUENCES', 'FUNCTIONS'):
            conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON {kind} FROM {role}')
    ensure_schema(conn)
    ensure_normalized_schema(conn)
    conn.execute('''CREATE TABLE IF NOT EXISTS product_feedback (
        id BIGSERIAL PRIMARY KEY, product_id BIGINT NOT NULL, helpful BOOLEAN NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS tracking_links (
        cache_key TEXT PRIMARY KEY, advertiser_id INTEGER NOT NULL, destination_url TEXT NOT NULL,
        tracking_url TEXT NOT NULL, parameters_json JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    for name in TABLES:
        conn.execute(f'ALTER TABLE public.{name} ENABLE ROW LEVEL SECURITY')
        for role in api_roles:
            conn.execute(f'REVOKE ALL ON TABLE public.{name} FROM {role}')
    for role in api_roles:
        conn.execute(f'REVOKE ALL ON TABLE public.catalog_search FROM {role}')
    # No API policies: direct SQL runs as the owner; anon/authenticated have no access.


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', required=True)
    parser.parse_args()
    settings = database_settings(project_root(), load_secrets())
    if settings.backend != 'postgres':
        raise SystemExit('PostgreSQL configuration required')
    with connect_database(settings) as conn:
        prepare_private_catalog(conn)
    print('Catalog prepared: Data API unchanged; public client access denied.')


if __name__ == '__main__':
    main()
