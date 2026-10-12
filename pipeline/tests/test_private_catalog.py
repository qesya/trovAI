import pytest

from trovai_pipeline.database import connect_database
from trovai_pipeline.private_catalog import TABLES, prepare_private_catalog
from trovai_pipeline.normalized_catalog import ensure_normalized_schema

pytestmark = pytest.mark.postgres


def test_private_catalog_is_idempotent_and_denies_public_access(database):
    with connect_database(database) as conn:
        prepare_private_catalog(conn)
        prepare_private_catalog(conn)
        rows = conn.execute("SELECT relname, relrowsecurity FROM pg_class WHERE relname = ANY(?) AND relkind = 'r'", (list(TABLES),)).fetchall()
        assert len(rows) == len(TABLES)
        assert all(enabled for _, enabled in rows)
        # A sync recreates the view: its invoker protection must survive.
        ensure_normalized_schema(conn)
        assert conn.execute("SELECT reloptions FROM pg_class WHERE relname = 'catalog_search'").fetchone()[0] == ['security_invoker=true']
        grants = conn.execute("""SELECT COUNT(*) FROM pg_class c, LATERAL aclexplode(c.relacl) a
            WHERE c.relnamespace = 'public'::regnamespace AND a.grantee = 0""").fetchone()[0]
        assert grants == 0
