import streamlit as st

from src.site_config import load_site_identity
from src.site_ui import render_footer, render_identity_setup_warning


st.set_page_config(page_title="Privacy · TrovAI", page_icon="🔐")
identity = load_site_identity(st.secrets)
owner = identity.owner or "[titolare da configurare]"
privacy_email = identity.privacy_email or "[email privacy da configurare]"

st.title("Informativa privacy")
st.caption(f"Ultimo aggiornamento: {identity.legal_last_updated}")
render_identity_setup_warning(identity)

st.subheader("Titolare e contatti")
st.write(f"Il titolare del trattamento è {owner}. Contatto privacy: {privacy_email}.")

st.subheader("Dati trattati")
st.write(
    "Il servizio tratta il testo delle ricerche, i filtri selezionati, le "
    "interazioni tecniche necessarie alla sessione e gli elementi aggiunti "
    "temporaneamente a preferiti o carrello. Non inserire dati personali, dati "
    "sensibili o informazioni di pagamento nella chat."
)

st.subheader("Finalità")
st.write(
    "I dati vengono utilizzati per interpretare la richiesta, cercare prodotti, "
    "mantenere la sessione e garantire sicurezza e funzionamento del servizio."
)

st.subheader("Fornitori tecnologici")
st.write(
    "Il testo della ricerca può essere trasmesso al fornitore del modello di "
    "intelligenza artificiale configurato dal gestore. Hosting, monitoraggio o "
    "analytics possono comportare ulteriori trattamenti e dovranno essere "
    "indicati qui prima della pubblicazione."
)

st.subheader("Conservazione")
st.write(
    "Nella versione attuale chat, preferiti e carrello sono conservati nello stato "
    "temporaneo della sessione. Eventuali log tecnici del servizio pubblicato "
    "dovranno avere tempi di conservazione documentati e limitati."
)

st.subheader("Link esterni")
st.write(
    "Quando apri il sito di un negozio si applicano la sua informativa privacy e "
    "le tecnologie di tracciamento del network o del venditore."
)

st.subheader("Diritti")
st.write(
    f"Per richieste relative ai tuoi dati puoi contattare {privacy_email}. "
    "Prima della pubblicazione questa sezione deve essere verificata rispetto "
    "alla configurazione reale del servizio e alla normativa applicabile."
)

render_footer(identity)
