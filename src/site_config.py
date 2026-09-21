"""Identita pubblica e recapiti del sito."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from src.config import get_setting


@dataclass(frozen=True)
class SiteIdentity:
    name: str
    owner: Optional[str]
    contact_email: Optional[str]
    privacy_email: Optional[str]
    legal_last_updated: str

    @property
    def is_complete(self) -> bool:
        return bool(self.owner and self.contact_email and self.privacy_email)


def load_site_identity(secrets: Optional[Mapping[str, Any]] = None) -> SiteIdentity:
    return SiteIdentity(
        name=get_setting("SITE_NAME", secrets, default="TrovAI") or "TrovAI",
        owner=get_setting("SITE_OWNER", secrets),
        contact_email=get_setting("CONTACT_EMAIL", secrets),
        privacy_email=get_setting("PRIVACY_EMAIL", secrets),
        legal_last_updated=get_setting(
            "LEGAL_LAST_UPDATED", secrets, default="19 agosto 2026"
        )
        or "19 agosto 2026",
    )
