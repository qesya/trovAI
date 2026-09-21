import streamlit as st

from src.site_config import load_site_identity
from src.site_ui import render_footer, render_identity_setup_warning


st.set_page_config(page_title="Contatti · TrovAI", page_icon="✉️")
identity = load_site_identity(st.secrets)

st.title("Contatti")
render_identity_setup_warning(identity)

st.write(
    "Puoi contattarci per assistenza sul funzionamento di TrovAI, segnalazioni "
    "relative ai risultati o richieste sulla privacy."
)

if identity.contact_email:
    st.link_button(
        "Scrivi al supporto", f"mailto:{identity.contact_email}", type="primary"
    )
    st.write(f"Supporto generale: {identity.contact_email}")
else:
    st.write("Supporto generale: [email da configurare]")

if identity.privacy_email:
    st.write(f"Richieste privacy: {identity.privacy_email}")
else:
    st.write("Richieste privacy: [email da configurare]")

st.info(
    "Per problemi con un ordine, un pagamento, una consegna o un reso devi "
    "contattare direttamente il negozio presso cui hai effettuato l'acquisto."
)

render_footer(identity)
