# TrovAI

Assistente allo shopping basato su Gemini: l'utente descrive cosa cerca in
linguaggio naturale e TrovAI confronta le offerte dei negozi affiliati Awin.

## Struttura del repository

| Cartella | Cosa contiene |
|---|---|
| [`pipeline/`](pipeline/README.md) | Import dei feed Awin, pulizia, arricchimento Gemini (attributi, titoli, immagini) e catalogo su **PostgreSQL**. |
| [`web/`](web/README.md) | Sito **Next.js**: ricerca in chat, filtri, pagine legali e link affiliati. Legge il catalogo creato dalla pipeline. |
| `docs/` | Bozze per candidature Awin e merchant. |
| `assets/` | Logo e palette del marchio. |

```
feed Awin ──> pipeline/ ──> PostgreSQL (vista catalog_search) ──> web/ ──> utente
```

## Avvio in locale

1. **Database:** un PostgreSQL raggiungibile (locale o Neon/Supabase).
2. **Pipeline:** dalla radice del repository
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e "pipeline[dev]"
   mkdir -p .streamlit && cp pipeline/secrets.example.toml .streamlit/secrets.toml   # oppure variabili d'ambiente (.env.example)
   trovai-sync --apply --ai-limit 50                           # importa il feed e crea le tabelle
   ```
   Senza feed reale puoi partire dal feed demo (dati fittizi, nessuna chiamata Gemini):
   ```bash
   AWIN_FEED_DOWNLOAD_URL="file://$PWD/pipeline/tests/fixtures/feed_demo.csv" trovai-sync --apply --ai-limit 0
   ```
3. **Sito:**
   ```bash
   cd web
   cp .env.example .env.local   # Gemini, stesso PostgreSQL della pipeline, dati del sito
   npm install
   npm run dev                  # http://localhost:3000
   ```

Non inserire mai credenziali reali in `.env.example`, nei file `*.example` o nel
codice sorgente. Per bloccare le chiavi gia' al momento del commit:
`pip install pre-commit && pre-commit install`.

## Controlli automatici

La CI (`.github/workflows/ci.yml`) esegue a ogni push e pull request:

- **pipeline:** ruff e pytest, compresi i test di integrazione su PostgreSQL;
- **sito:** lint, controllo dei tipi e build; poi avvia il sito su un database
  riempito dalla pipeline con un feed di prova e verifica `/api/health`;
- **segreti:** gitleaks su tutto il repository.

## Link affiliati e click reference

Per impostazione predefinita il sito usa il link Awin presente nel product feed
(`aw_deep_link`). Il Link Builder API si attiva con `AWIN_PUBLISHER_ID`,
`AWIN_API_TOKEN`, `AWIN_LINK_BUILDER_ENABLED=true` e, opzionalmente,
`AWIN_TRACKING_CAMPAIGN`. I link generati restano sette giorni nella tabella
`tracking_links`. Le click reference contengono solo ID dell'offerta e posizione
del risultato, mai il testo della ricerca o dati personali.

Il feed Awin va creato includendo soltanto advertiser per cui il rapporto risulta
`Joined`.

## Ordinamento dei risultati

Gemini trasforma il linguaggio naturale in filtri strutturati. Prezzi,
disponibilita', esclusioni e ordinamento sono gestiti localmente: il ranking assegna
punti dichiarati a marca, categoria, colore, materiale, taglia, genere, negozio e
parole chiave, e mostra fino a tre motivazioni per prodotto. La commissione non e'
un fattore di ranking. I testi di trasparenza sono in `web/src/lib/disclosures.ts`.

Il feedback sui risultati salva soltanto ID dell'offerta, valore e data.

## Sicurezza

- Richieste limitate a 500 caratteri e ripulite dai caratteri di controllo.
- Al massimo 8 ricerche al minuto per IP (in memoria nel processo Next.js: in
  produzione serve anche un limite a livello di proxy/CDN).
- La cronologia inviata a Gemini contiene solo i filtri strutturati ammessi.
- `GET /api/health` verifica configurazione, database e offerte disponibili senza
  mostrare segreti.

Le pagine privacy e termini descrivono il prototipo e non sostituiscono una
revisione legale. Vedi anche [`PRODUCTION_CHECKLIST.md`](PRODUCTION_CHECKLIST.md).
