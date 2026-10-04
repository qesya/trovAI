"""Ritmo delle richieste e ritentativi per le chiamate Gemini.

Unica implementazione condivisa da import feed, titoli, immagini e test
isolato: prima ogni script aveva una propria variante leggermente diversa.
"""

from __future__ import annotations

import re
import time
from typing import Callable, TypeVar

T = TypeVar("T")

# Free Tier Flash-Lite: 15 richieste/minuto -> una ogni 4,3 secondi.
FREE_TIER_INTERVAL_SECONDS = 4.3
MAX_RETRIES = 4
DEFAULT_RATE_LIMIT_WAIT_SECONDS = 30.0


class RateLimiter:
    """Garantisce un intervallo minimo tra due richieste consecutive."""

    def __init__(self, interval_seconds: float = FREE_TIER_INTERVAL_SECONDS,
                 *, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.interval_seconds = interval_seconds
        self._clock = clock
        self._sleep = sleep
        self._last_request_at: float | None = None

    def wait(self) -> None:
        if self._last_request_at is not None:
            elapsed = self._clock() - self._last_request_at
            if elapsed < self.interval_seconds:
                self._sleep(self.interval_seconds - elapsed)
        self._last_request_at = self._clock()


def is_rate_limit_error(error: Exception) -> bool:
    message = str(error)
    return "429" in message or "resource_exhausted" in message.lower()


def retry_delay(error: Exception, *, minimum: float,
                default: float = DEFAULT_RATE_LIMIT_WAIT_SECONDS) -> float | None:
    """Secondi da attendere per un errore di quota; None se non e' un errore di quota."""
    if not is_rate_limit_error(error):
        return None
    match = re.search(r"retry in\s+([0-9.]+)\s*s", str(error), flags=re.IGNORECASE)
    return max(float(match.group(1)) + 1.0, minimum) if match else max(default, minimum)


def call_with_retry(action: Callable[[], T], *, limiter: RateLimiter | None = None,
                    minimum_wait: float = FREE_TIER_INTERVAL_SECONDS,
                    default_wait: float = DEFAULT_RATE_LIMIT_WAIT_SECONDS,
                    max_retries: int = MAX_RETRIES,
                    sleep: Callable[[float], None] | None = None) -> T:
    """Esegue ``action`` rispettando il ritmo e ritentando SOLO i limiti di quota.

    Gli altri errori vengono rilanciati subito: devono essere visibili, non
    trasformati in un risultato vuoto.
    """
    for attempt in range(1, max_retries + 1):
        if limiter is not None:
            limiter.wait()
        try:
            return action()
        except Exception as exc:
            delay = retry_delay(exc, minimum=minimum_wait, default=default_wait)
            if delay is None or attempt == max_retries:
                raise
            print(f"PAUSA QUOTA: attendo {delay:.0f}s e ritento ({attempt}/{max_retries}).")
            (sleep or time.sleep)(delay)
    raise RuntimeError("Tentativi Gemini esauriti.")  # pragma: no cover
