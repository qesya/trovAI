"""Connessioni locali al catalogo: SQLite storico o PostgreSQL."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional


def _prefer_official_postgres_library_on_windows() -> None:
    """Evita la DLL bundled bloccata da Smart App Control su alcuni PC Windows.

    Quando PostgreSQL e installato localmente, psycopg puo usare la sua libpq
    ufficiale tramite l'implementazione Python. La verifica di sicurezza di
    Windows resta attiva: non vengono accettate DLL non attendibili.
    """
    if os.name != "nt" or os.getenv("PSYCOPG_IMPL"):
        return
    program_files = Path(os.environ.get("ProgramFiles", r"C:\\Program Files"))
    postgresql_root = program_files / "PostgreSQL"
    if not postgresql_root.is_dir():
        return
    candidates = sorted(
        (path / "bin" for path in postgresql_root.iterdir() if path.is_dir()),
        key=lambda path: path.name,
        reverse=True,
    )
    for bin_dir in candidates:
        if (bin_dir / "libpq.dll").is_file():
            os.environ["PSYCOPG_IMPL"] = "python"
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
            return


_prefer_official_postgres_library_on_windows()

try:
    import psycopg
except ImportError:  # Il messaggio utile viene mostrato solo se PostgreSQL è richiesto.
    psycopg = None


class DatabaseConfigurationError(RuntimeError):
    """Configurazione del database mancante o incoerente."""


DATABASE_ERRORS = (sqlite3.Error,) + ((psycopg.Error,) if psycopg else ())


@dataclass(frozen=True)
class DatabaseSettings:
    backend: str
    sqlite_path: Optional[Path] = None
    host: Optional[str] = None
    port: int = 5432
    database: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None

    @property
    def cache_key(self) -> str:
        if self.backend == "postgres":
            return f"postgres:{self.host}:{self.port}:{self.database}:{self.user}"
        return f"sqlite:{self.sqlite_path}"


def _setting(name: str, values: Optional[Mapping[str, Any]]) -> Optional[str]:
    if values is None:
        return None
    try:
        value = values.get(name)
    except Exception:
        value = None
    return str(value).strip() if value is not None and str(value).strip() else None


def database_settings(
    base_dir: Path,
    values: Optional[Mapping[str, Any]] = None,
    sqlite_path: Optional[str] = None,
) -> DatabaseSettings:
    """Preferisce PostgreSQL quando sono presenti tutte le cinque impostazioni."""
    postgres = {
        "host": _setting("POSTGRES_HOST", values),
        "port": _setting("POSTGRES_PORT", values),
        "database": _setting("POSTGRES_DATABASE", values),
        "user": _setting("POSTGRES_USER", values),
        "password": _setting("POSTGRES_PASSWORD", values),
    }
    configured = [value for value in postgres.values() if value]
    if configured:
        missing = [name for name, value in postgres.items() if not value]
        if missing:
            raise DatabaseConfigurationError(
                "Configurazione PostgreSQL incompleta: mancano " + ", ".join(missing)
            )
        try:
            port = int(postgres["port"] or 5432)
        except ValueError as exc:
            raise DatabaseConfigurationError("POSTGRES_PORT deve essere numerico") from exc
        return DatabaseSettings(
            backend="postgres",
            host=postgres["host"],
            port=port,
            database=postgres["database"],
            user=postgres["user"],
            password=postgres["password"],
        )

    candidate = Path(sqlite_path or "shop_database.db").expanduser()
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return DatabaseSettings(backend="sqlite", sqlite_path=candidate)


def _qmark_to_percent(sql: str) -> str:
    """Converte i parametri SQLite usati dal progetto in parametri PostgreSQL."""
    return sql.replace("?", "%s")


class _PostgresCursor:
    def __init__(self, cursor: Any):
        self._cursor = cursor

    def execute(self, sql: str, params: Any = None):
        self._cursor.execute(_qmark_to_percent(sql), params)
        return self

    def executemany(self, sql: str, params_seq: Any):
        self._cursor.executemany(_qmark_to_percent(sql), params_seq)
        return self

    def __getattr__(self, name: str):
        return getattr(self._cursor, name)


class PostgresConnection:
    """Piccolo adattatore DB-API per riusare le query esistenti con PostgreSQL."""

    backend = "postgres"

    def __init__(self, settings: DatabaseSettings):
        if psycopg is None:
            raise DatabaseConfigurationError(
                "Manca psycopg. Attiva .venv-local e installa le dipendenze."
            )
        self._connection = psycopg.connect(
            host=settings.host,
            port=settings.port,
            dbname=settings.database,
            user=settings.user,
            password=settings.password,
        )

    def execute(self, sql: str, params: Any = None) -> _PostgresCursor:
        cursor = _PostgresCursor(self._connection.cursor())
        return cursor.execute(sql, params)

    def executemany(self, sql: str, params_seq: Any) -> _PostgresCursor:
        cursor = _PostgresCursor(self._connection.cursor())
        return cursor.executemany(sql, params_seq)

    def cursor(self) -> _PostgresCursor:
        return _PostgresCursor(self._connection.cursor())

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()
        return False


def connect_database(settings: DatabaseSettings):
    if settings.backend == "postgres":
        return PostgresConnection(settings)
    if settings.sqlite_path is None:
        raise DatabaseConfigurationError("Percorso SQLite mancante")
    return sqlite3.connect(settings.sqlite_path)


def is_postgres_connection(connection: Any) -> bool:
    return getattr(connection, "backend", "") == "postgres"
