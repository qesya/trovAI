import streamlit as st

from src.disclosures import AI_DISCLOSURE, MERCHANT_DISCLOSURE, RANKING_DISCLOSURE
from src.site_config import load_site_identity
from src.site_ui import render_affiliate_notice, render_footer


st.set_page_config(page_title="Come funziona · TrovAI", page_icon="🔎")
identity = load_site_identity(st.secrets)

st.title("Come funziona TrovAI")
st.write(
    "TrovAI aiuta a cercare prodotti in un catalogo di negozi terzi usando "
    "linguaggio naturale e filtri tradizionali. Non vende direttamente prodotti."
)

st.subheader("1. Comprendiamo la richiesta")
st.write(
    "Il testo inserito viene analizzato per individuare caratteristiche come "
    "categoria, marca, colore, taglia e fascia di prezzo."
)

st.subheader("2. Interroghiamo il catalogo")
st.write(
    "I filtri vengono applicati al catalogo disponibile. Prezzi, immagini, "
    "disponibilità e descrizioni provengono dai dati associati ai negozi."
)

st.subheader("3. Ordiniamo i risultati")
st.write(RANKING_DISCLOSURE)
st.write(AI_DISCLOSURE)

st.subheader("4. Completi l'acquisto sul sito del negozio")
st.write(MERCHANT_DISCLOSURE)

render_affiliate_notice()
render_footer(identity)
