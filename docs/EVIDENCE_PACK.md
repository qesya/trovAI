# Pacchetto evidenze Awin

Raccogliere questi elementi dopo il deploy e conservarli con data e versione.

## Evidenze pubbliche

- [ ] Screenshot desktop e mobile della homepage.
- [ ] Screenshot della disclosure visibile prima dei link.
- [ ] Screenshot di un prodotto Awin con data feed e link affiliato.
- [ ] Screenshot delle pagine privacy, termini, trasparenza e contatti.
- [ ] URL pubblico e data di verifica HTTPS.

## Evidenze tecniche

- [ ] Output di `python -m unittest discover -s tests -v`.
- [ ] Output di `python healthcheck.py` con `ready: true`.
- [ ] Output di `python awin_readiness.py` per il gate pertinente.
- [ ] Risultato dell'ultimo sync nella tabella `feed_sync`.
- [ ] Evidenza che tutti i prodotti Awin attivi hanno `aw_deep_link`.
- [ ] Click di prova visibile nel reporting con `clickref`, `clickref2`, `clickref3`.

## Evidenze organizzative

- [ ] Titolare, contatti e residenza fiscale verificati.
- [ ] Fonti di traffico documentate senza stime presentate come dati reali.
- [ ] Diritti su contenuti, immagini e dati confermati.
- [ ] Registro dei termini dei merchant e delle successive variazioni.
- [ ] Procedura per rimuovere rapidamente merchant o prodotti non conformi.
- [ ] Procedura di revoca e rotazione dei token.

## Elementi da non includere

- token API o chiavi datafeed;
- chiave Gemini;
- prompt degli utenti;
- database completo;
- log contenenti dati personali;
- metriche inventate o non verificabili.
