# Checklist di pubblicazione

Questa checklist deve essere completata sull'ambiente di hosting, non soltanto nel
codice sorgente.

## Identita e conformita

- [ ] `SITE_OWNER`, `CONTACT_EMAIL` e `PRIVACY_EMAIL` contengono dati reali.
- [ ] Privacy, termini e disclosure sono stati revisionati sulla configurazione reale.
- [ ] Il profilo Awin descrive correttamente sito, traffico e metodo promozionale.
- [ ] Sono mostrati soltanto advertiser per cui il rapporto risulta `Joined`.

## Segreti

- [ ] La vecchia chiave Gemini esposta e stata revocata.
- [ ] Gemini, Awin datafeed e Awin API token sono conservati nel secret manager.
- [ ] I token non compaiono in log, immagini, backup o variabili del client browser.
- [ ] E documentata una procedura di rotazione e revoca.

## Hosting e rete

- [ ] Dominio definitivo con HTTPS valido e redirect permanente da HTTP.
- [ ] Rate limiting per IP o account davanti a Streamlit.
- [ ] Limite alla dimensione delle richieste e timeout a livello di proxy.
- [ ] Security header verificati: CSP, HSTS, X-Content-Type-Options e frame policy.
- [ ] Accesso amministrativo e deploy protetti con autenticazione forte.

## Dati e operativita

- [ ] Backup cifrati del database e prova documentata di ripristino.
- [ ] Conservazione dei log definita e limitata.
- [ ] Log privi di prompt, token e URL contenenti chiavi.
- [ ] Monitor per errori, feed non aggiornati, prodotti attivi e link non validi.
- [ ] Sincronizzazione feed eseguita con lock per evitare job concorrenti.
- [ ] Ambiente di staging separato dalla produzione.

## Verifica finale

- [ ] `python -m unittest discover -s tests -v` passa.
- [ ] `python healthcheck.py` restituisce `"ready": true`.
- [ ] Un click reale appare nel reporting Awin con i click reference attesi.
- [ ] Prezzo e disponibilita sono coerenti tra TrovAI e pagina del merchant.
- [ ] Cancellazione sessione, pagine legali e contatti funzionano da mobile.
