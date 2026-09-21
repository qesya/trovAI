# TrovAI

Prototipo Streamlit di assistente allo shopping basato su Gemini e un catalogo
SQLite locale.

## Configurazione locale

1. Crea e attiva un ambiente virtuale Python.
2. Installa le dipendenze con `python -m pip install -r requirements.txt`.
3. Imposta `GEMINI_API_KEY` nell'ambiente oppure copia
   `.streamlit/secrets.toml.example` in `.streamlit/secrets.toml` e inserisci una
   nuova chiave.
4. Configura `SITE_OWNER`, `CONTACT_EMAIL` e `PRIVACY_EMAIL` con dati reali.
5. Genera il catalogo dimostrativo con `python awin_db.py`, oppure configura
   `DATABASE_PATH` per usare un altro database compatibile.
6. Avvia l'app con `streamlit run awin_app5.py`.

Non inserire mai credenziali reali in `.env.example`, nei file `*.example` o nel
codice sorgente.

## Test

```bash
python -m unittest discover -s tests -v
```

I prodotti del catalogo dimostrativo usano normali collegamenti esterni e non
vengono presentati come tracking Awin. Solo i prodotti importati da feed Awin
possono usare `aw_deep_link` o link creati dal Link Builder ufficiale.

Le pagine privacy e termini descrivono il prototipo corrente e non sostituiscono
una revisione legale basata su titolare, hosting, analytics, log e fornitori
effettivamente utilizzati in produzione.

## Sincronizzazione product feed Awin

La sincronizzazione usa la Product Feed List di Awin e importa esclusivamente gli
advertiser inclusi in `AWIN_ADVERTISER_IDS` che risultano `Joined` per il publisher.
La chiave dei product feed è distinta dal token della Publisher API.

1. Configura `AWIN_DATAFEED_API_KEY` fuori dal repository.
2. Configura `AWIN_ADVERTISER_IDS` con una lista esplicita di ID separati da virgola.
3. Esegui `python awin_feed_sync.py`.

I prodotti assenti da un successivo aggiornamento dello stesso feed vengono
marcati come non disponibili. Il catalogo creato da `awin_db.py` rimane invece una
demo e viene identificato come tale nell'interfaccia.

## Link Builder e click reference

Per impostazione predefinita l'app usa il link Awin gia presente nel product feed.
Il Link Builder API puo essere attivato dopo aver configurato:

- `AWIN_PUBLISHER_ID`;
- `AWIN_API_TOKEN`;
- `AWIN_LINK_BUILDER_ENABLED=true`;
- opzionalmente `AWIN_TRACKING_CAMPAIGN`.

Il token Publisher API usa autenticazione Bearer ed e diverso dalla chiave dei
product feed. I link generati vengono conservati per sette giorni nella tabella
locale `tracking_links`, riducendo il numero di chiamate API. Le click reference
contengono esclusivamente ID del prodotto e posizione del risultato; non includono
testo della ricerca o dati personali. Se il Link Builder non e disponibile, viene
usato l'`aw_deep_link` ufficiale del feed.

## Ordinamento dei risultati

Gemini viene usato per trasformare il linguaggio naturale in filtri strutturati.
Prezzi, disponibilita, esclusioni, conteggio e ordinamento vengono invece gestiti
localmente. Il ranking assegna punti dichiarati a marca, categoria, colore,
materiale, taglia, genere, merchant e parole chiave; l'interfaccia mostra fino a
tre motivazioni per prodotto.

Il feedback positivo o negativo salva soltanto ID del prodotto, valore del feedback
e data. Non vengono registrati testo della ricerca o identificatori dell'utente.

## Disclosure commerciale

I testi pubblici relativi ad affiliazioni, ranking, ruolo dell'AI e responsabilita
del merchant sono centralizzati in `src/disclosures.py`. La disclosure viene
mostrata prima dei risultati e ripetuta vicino ai link affiliati. La commissione
non e inclusa nei fattori di ranking.

## Sicurezza e readiness

- Le richieste sono limitate a 500 caratteri e ripulite dai caratteri di controllo.
- Ogni sessione puo effettuare al massimo 8 ricerche in 60 secondi.
- La cronologia inviata al modello contiene solo filtri strutturati ammessi, non il
  messaggio originale, parole chiave libere o caratteristiche indesiderate libere.
- Il comando `python healthcheck.py` verifica database, schema, prodotti attivi e
  presenza delle configurazioni obbligatorie senza stampare i segreti.
- Gli errori di download dei feed non includono URL che potrebbero contenere la
  chiave datafeed.

Il rate limiting di sessione non sostituisce un limite per IP o account applicato
da reverse proxy, CDN o piattaforma di hosting. Prima della produzione configurare
anche HTTPS, security header, limiti di richiesta, backup, monitoraggio, rotazione
dei segreti e una politica documentata di conservazione dei log.

## Readiness Awin

`python awin_readiness.py` valuta separatamente:

- `network_application_ready`: sito pubblico, identita, pagine, diritti sui
  contenuti e catalogo funzionante;
- `merchant_application_ready`: requisiti precedenti piu Publisher ID;
- `merchant_launch_ready`: prodotti Awin reali, deep link completi, nessun prodotto
  demo attivo e click di prova confermato.

Il comando non invia candidature e non mostra valori di credenziali o dati
societari. Le bozze da compilare sono nella cartella `docs/`.

## Sicurezza

Una chiave Gemini era precedentemente inclusa nel prototipo. La sua rimozione dal
file non la disattiva: deve essere revocata nel progetto Google che l'ha emessa e
sostituita con una nuova chiave configurata fuori dal repository.
