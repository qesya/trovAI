import streamlit as st

from src.disclosures import AFFILIATE_DISCLOSURE, RANKING_DISCLOSURE
from src.site_config import load_site_identity
from src.site_ui import render_footer, render_identity_setup_warning


st.set_page_config(page_title="Termini · TrovAI", page_icon="📄")
identity = load_site_identity(st.secrets)

st.title("Termini d'uso")
st.caption(f"Ultimo aggiornamento: {identity.legal_last_updated}")
render_identity_setup_warning(identity)

st.subheader("Natura del servizio")
st.write(
    "TrovAI è uno strumento informativo di ricerca e confronto. Non è il "
    "venditore, non conclude il contratto di acquisto e non incassa il pagamento."
)

st.subheader("Accuratezza delle informazioni")
st.write(
    "Cerchiamo di mostrare dati aggiornati, ma prezzi, disponibilità, immagini e "
    "condizioni possono contenere ritardi o errori. Prima dell'ordine fanno fede "
    "le informazioni pubblicate dal negozio."
)

st.subheader("Risposte generate con AI")
st.write(
    "L'intelligenza artificiale può interpretare in modo inesatto una richiesta. "
    "I risultati non costituiscono consulenza professionale né garanzia di "
    "idoneità di un prodotto."
)

st.subheader("Acquisti e assistenza")
st.write(
    "Ordini, pagamenti, spedizioni, garanzie, resi e rimborsi sono disciplinati "
    "dai termini del negozio scelto e devono essere gestiti con quel negozio."
)

st.subheader("Uso consentito")
st.write(
    "Non è consentito utilizzare il servizio per attività illecite, tentare di "
    "comprometterne la sicurezza o effettuare interrogazioni automatizzate che ne "
    "pregiudichino il funzionamento."
)

st.subheader("Affiliazioni")
st.write(AFFILIATE_DISCLOSURE)
st.write(RANKING_DISCLOSURE)

render_footer(identity)
