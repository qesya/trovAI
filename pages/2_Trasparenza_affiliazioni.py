import streamlit as st

from src.disclosures import (
    AI_DISCLOSURE,
    MERCHANT_DISCLOSURE,
    RANKING_DISCLOSURE,
)
from src.site_config import load_site_identity
from src.site_ui import render_affiliate_notice, render_footer


st.set_page_config(page_title="Affiliazioni · TrovAI", page_icon="🤝")
identity = load_site_identity(st.secrets)

st.title("Trasparenza e affiliazioni")
render_affiliate_notice()

st.subheader("Che cosa significa")
st.write(
    "Un link affiliato consente di attribuire al nostro servizio una visita o un "
    "eventuale acquisto. La commissione viene riconosciuta dal negozio o dal "
    "network di affiliazione e non aggiunge un costo specifico al tuo ordine."
)

st.subheader("Come ordiniamo i risultati")
st.write(RANKING_DISCLOSURE)
st.write(
    "I fattori considerati sono marca, tipologia, sottocategoria, colore, "
    "materiale, genere, taglia, negozio e corrispondenza delle parole chiave. "
    "A parità di punteggio viene mantenuto un ordine stabile."
)

st.subheader("Ruolo dell'intelligenza artificiale")
st.write(AI_DISCLOSURE)

st.subheader("Rapporto con negozi e network")
st.write(
    "La presenza di un link non implica che il negozio, Awin o un altro network "
    "abbia sponsorizzato, approvato o realizzato TrovAI. Eventuali marchi "
    "appartengono ai rispettivi titolari."
)

st.subheader("Dati commerciali")
st.write(
    "Prezzi, sconti e disponibilità possono cambiare. Fanno fede esclusivamente "
    "le condizioni mostrate dal negozio prima dell'acquisto."
)

st.subheader("Chi conclude la vendita")
st.write(MERCHANT_DISCLOSURE)

render_footer(identity)
