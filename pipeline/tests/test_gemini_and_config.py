from __future__ import annotations

import pytest

from trovai_pipeline import config
from trovai_pipeline.gemini import RateLimiter, call_with_retry, retry_delay


class FakeClock:
    def __init__(self):
        self.now = 100.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


# --- Rate limit e ritentativi -------------------------------------------------------

def test_rate_limiter_spaces_requests():
    clock = FakeClock()
    limiter = RateLimiter(4.3, clock=clock, sleep=clock.sleep)
    limiter.wait()           # prima richiesta: nessuna attesa
    clock.now += 1.0
    limiter.wait()           # 1s dopo: attende i 3,3s mancanti
    assert clock.sleeps == [pytest.approx(3.3)]


def test_retry_delay_reads_google_hint():
    error = RuntimeError("429 RESOURCE_EXHAUSTED. Please retry in 12.5s.")
    assert retry_delay(error, minimum=4.3) == pytest.approx(13.5)


def test_retry_delay_default_and_non_quota_errors():
    assert retry_delay(RuntimeError("429 Too Many Requests"), minimum=4.3, default=30) == 30
    assert retry_delay(ValueError("JSON non valido"), minimum=4.3) is None


def test_call_with_retry_retries_only_quota_errors():
    calls = {"n": 0}
    sleeps: list[float] = []

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("429 resource_exhausted retry in 1s")
        return "ok"

    assert call_with_retry(flaky, minimum_wait=0, sleep=sleeps.append) == "ok"
    assert calls["n"] == 3
    assert sleeps == [2.0, 2.0]


def test_call_with_retry_raises_other_errors_immediately():
    calls = {"n": 0}

    def broken():
        calls["n"] += 1
        raise ValueError("risposta non valida")

    with pytest.raises(ValueError):
        call_with_retry(broken, sleep=lambda _: None)
    assert calls["n"] == 1


def test_call_with_retry_gives_up_after_max_retries():
    def always_quota():
        raise RuntimeError("429")

    with pytest.raises(RuntimeError):
        call_with_retry(always_quota, max_retries=3, sleep=lambda _: None)


# --- Configurazione -------------------------------------------------------------------

def test_load_secrets_without_file_or_env_is_empty():
    assert config.load_secrets() == {}


def test_load_secrets_reads_toml(tmp_path):
    (tmp_path / ".streamlit").mkdir()
    (tmp_path / ".streamlit" / "secrets.toml").write_text('POSTGRES_HOST = "db.local"\nALTRO = "x"\n')
    assert config.load_secrets() == {"POSTGRES_HOST": "db.local", "ALTRO": "x"}


def test_env_overrides_toml(tmp_path, monkeypatch):
    (tmp_path / ".streamlit").mkdir()
    (tmp_path / ".streamlit" / "secrets.toml").write_text('POSTGRES_HOST = "db.local"\n')
    monkeypatch.setenv("POSTGRES_HOST", "db.cloud")
    monkeypatch.setenv("GEMINI_FEED_API_KEY", "  chiave  ")
    monkeypatch.setenv("PATH_NON_PERTINENTE", "x")
    values = config.load_secrets()
    assert values["POSTGRES_HOST"] == "db.cloud"
    assert values["GEMINI_FEED_API_KEY"] == "chiave"
    assert "PATH_NON_PERTINENTE" not in values


def test_empty_env_value_does_not_override(tmp_path, monkeypatch):
    (tmp_path / ".streamlit").mkdir()
    (tmp_path / ".streamlit" / "secrets.toml").write_text('POSTGRES_HOST = "db.local"\n')
    monkeypatch.setenv("POSTGRES_HOST", "")
    assert config.load_secrets()["POSTGRES_HOST"] == "db.local"


def test_custom_secrets_file(tmp_path, monkeypatch):
    custom = tmp_path / "altrove.toml"
    custom.write_text('AWIN_FEED_DOWNLOAD_URL = "https://feed"\n')
    monkeypatch.setenv("TROVAI_SECRETS_FILE", str(custom))
    assert config.load_secrets()["AWIN_FEED_DOWNLOAD_URL"] == "https://feed"


def test_load_secrets_reads_env_file(tmp_path):
    (tmp_path / ".env").write_text(
        "# commento\n"
        "export DATABASE_URL='postgresql://u:p@db.example/neondb?sslmode=require'\n"
        'GEMINI_API_KEY="abc"\n'
        "POSTGRES_PORT=5432  # commento in linea\n"
        "VUOTA=\n"
    )
    values = config.load_secrets()
    assert values["DATABASE_URL"] == "postgresql://u:p@db.example/neondb?sslmode=require"
    assert values["GEMINI_API_KEY"] == "abc"
    assert values["POSTGRES_PORT"] == "5432"
    assert "VUOTA" not in values


def test_env_file_overrides_toml_and_env_overrides_env_file(tmp_path, monkeypatch):
    (tmp_path / ".streamlit").mkdir()
    (tmp_path / ".streamlit" / "secrets.toml").write_text('POSTGRES_HOST = "toml"\nPOSTGRES_USER = "toml"\n')
    (tmp_path / ".env").write_text("POSTGRES_HOST=dotenv\nPOSTGRES_USER=dotenv\n")
    monkeypatch.setenv("POSTGRES_USER", "ambiente")
    values = config.load_secrets()
    assert values["POSTGRES_HOST"] == "dotenv"
    assert values["POSTGRES_USER"] == "ambiente"


# --- DATABASE_URL ----------------------------------------------------------------------

def test_database_url_remote_requires_ssl(tmp_path):
    from trovai_pipeline.database import database_settings

    settings = database_settings(
        tmp_path, {"DATABASE_URL": "postgresql://neon%40user:p%2Fss@ep-x.eu-central-1.aws.neon.tech/neondb"}
    )
    assert settings.backend == "postgres"
    assert settings.host == "ep-x.eu-central-1.aws.neon.tech"
    assert settings.port == 5432
    assert settings.database == "neondb"
    assert settings.user == "neon@user"
    assert settings.password == "p/ss"
    assert settings.sslmode == "require"


def test_database_url_wins_over_postgres_vars_and_keeps_explicit_sslmode(tmp_path):
    from trovai_pipeline.database import database_settings

    settings = database_settings(
        tmp_path,
        {
            "DATABASE_URL": "postgres://u:p@localhost:6543/db?sslmode=disable",
            "POSTGRES_HOST": "altro",
        },
    )
    assert (settings.host, settings.port, settings.database, settings.sslmode) == ("localhost", 6543, "db", "disable")


def test_database_url_localhost_without_ssl(tmp_path):
    from trovai_pipeline.database import database_settings

    assert database_settings(tmp_path, {"DATABASE_URL": "postgresql://u@localhost/db"}).sslmode is None


@pytest.mark.parametrize(
    "url",
    ["mysql://u:p@h/db", "postgresql://u:p@h/", "postgresql://h/db", "postgresql://u:p@h:abc/db"],
)
def test_database_url_invalid(tmp_path, url):
    from trovai_pipeline.database import DatabaseConfigurationError, database_settings

    with pytest.raises(DatabaseConfigurationError):
        database_settings(tmp_path, {"DATABASE_URL": url})
