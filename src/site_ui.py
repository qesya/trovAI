"""Elementi UI condivisi dalle pagine pubbliche."""

from __future__ import annotations

import streamlit as st

from src.disclosures import AFFILIATE_DISCLOSURE, RANKING_DISCLOSURE
from src.site_config import SiteIdentity


def render_affiliate_notice() -> None:
    st.info(f"{AFFILIATE_DISCLOSURE}\n\n{RANKING_DISCLOSURE}")


def render_identity_setup_warning(identity: SiteIdentity) -> None:
    if not identity.is_complete:
        st.warning(
            "Questa pagina contiene informazioni legali da completare prima "
            "della pubblicazione. Configura SITE_OWNER, CONTACT_EMAIL e "
            "PRIVACY_EMAIL."
        )


def render_footer(identity: SiteIdentity) -> None:
    st.divider()
    owner = identity.owner or "Titolare da configurare"
    contact = identity.contact_email or "Contatto da configurare"
    st.caption(
        f"{identity.name} · Gestito da {owner} · Contatti: {contact} · "
        "Acquisti, pagamenti, consegne e resi sono gestiti dai rispettivi negozi."
    )
