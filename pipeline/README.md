# TrovAI – pipeline feed Awin

Importa i feed affiliati Awin, normalizza i prodotti moda, usa Gemini per
attributi e titoli, crea embedding e tag visivi delle immagini e salva tutto in
PostgreSQL (prodotto → colore → taglia → offerta del negozio).

## Struttura

```
trovai_pipeline/
├── config.py            # chiavi da variabili d'ambiente o .streamlit/secrets.toml
├── gemini.py            # ritmo richieste e ritentativi (unico per tutto il progetto)
├── database.py          # connessione PostgreSQL / SQLite
├── feed_cleaner.py      # regole di pulizia + revisione Gemini dei campi
├── normalized_catalog.py# albero prodotto/colore/variante/offerta
├── awin_sync.py         # download feed, import iniziale e sincronizzazione
├── title_review.py      # titoli utente formulati da Gemini
├── image_embeddings.py  # embedding immagini
├── visual_tags.py       # tag visivi
├── schema.py            # tabella prodotti (creata dalla pipeline su un database vuoto)
├── visual_sample.py     # revisione colore feed vs foto (+ vecchia prova a 10 prodotti)
├── pipeline.py          # pipeline completa in 4 fasi
└── isolated_test.py     # prova su pochi prodotti, scrive solo catalogo_prova_visivo_10
tests/                   # pytest (unit + integrazione PostgreSQL)
```

## Installazione

Dalla radice del repository (macOS / Linux):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e "pipeline[dev]"
pre-commit install          # blocca i commit che contengono chiavi o password
```

Su Windows: `python -m venv .venv` e `.\.venv\Scripts\Activate.ps1`.

## Configurazione

Due modi, anche combinati (le variabili d'ambiente vincono):

1. **In locale:** copia `secrets.example.toml` in `.streamlit/secrets.toml` e compilalo.
2. **In CI o su un server:** imposta le variabili elencate in `.env.example`
   (su GitHub: *Settings → Secrets and variables → Actions*).

`.streamlit/secrets.toml` e `.env` sono esclusi da Git tramite `.gitignore`.

## Comandi

Lanciali dalla radice del repository, dove si trova `.streamlit/secrets.toml` (oppure imposta `TROVAI_HOME`).

```bash
# Anteprima: non scarica e non scrive nulla
trovai-pipeline

# Test controllato: 50 prodotti, 10 immagini
trovai-pipeline --apply --replace-catalog --catalog-limit 50 --feed-ai-limit 50 --title-ai-limit 50 --image-limit 10

# Aggiornamento incrementale (prezzi, disponibilita', nuovi prodotti)
trovai-sync --apply --ai-limit 500

# Prova isolata su 10 prodotti, non tocca il catalogo principale
trovai-isolated-test --apply --limit 10
```

Equivalenti senza installazione: `python -m trovai_pipeline.pipeline ...`,
`python -m trovai_pipeline.awin_sync ...`.

## Test

```bash
cd pipeline && pytest -q
```

I test di integrazione girano solo se indichi un database **usa-e-getta**
(lo schema `public` viene cancellato e ricreato):

```bash
TROVAI_TEST_DATABASE_URL="postgresql://postgres:password@localhost:5432/trovai_test" pytest -q
```

Su GitHub la CI (`.github/workflows/ci.yml`) li esegue a ogni push con un
PostgreSQL dedicato, insieme a `ruff` e alla ricerca di chiavi con gitleaks.

## Modifiche della fase 0 (2026-10-04)

- Codice riorganizzato nel pacchetto `trovai_pipeline`, installabile con comandi `trovai-*`.
- La pipeline crea da sola la tabella `prodotti` (prima la creava l'app
  Streamlit): un database vuoto viene inizializzato completamente. Su un
  database esistente aggiunge solo le colonne mancanti.
- Schema `prodotti` allineato a quello originale dell'app (`awin_db.py`):
  stesse colonne e, su un database nuovo, stessi vincoli.
- La pipeline non dipende da Streamlit; il sito e' in `web/` (Next.js) e legge
  la vista `catalog_search`. `.streamlit/secrets.toml` resta leggibile per
  comodita' in locale, accanto alle variabili d'ambiente.
- Chiavi lette anche da variabili d'ambiente (necessario per CI e server).
- Gestione quota Gemini unificata in `gemini.py`; l'import iniziale ora rispetta
  il ritmo del Free Tier e ritenta i 429.
- Gli errori Gemini nella revisione del feed non vengono piu' nascosti: sono
  ritentati (quota) o contati in `ai_failed`.
- Bug corretti nelle regole: "taglia unica" → "taglia taglia unicaca"; taglie
  "S, M, L" lette come una sola; "38,5" → "38 5"; "taglia unica" e frammenti
  "in e" lasciati nel titolo; blazer non classificato; colori femminili/plurali
  ("nera", "bianche") non riconosciuti; una categoria non valida di Gemini
  cancellava quella corretta.
- `NORMALIZATION_VERSION` portata a `2026-10-04`: al prossimo import i prodotti
  vengono rianalizzati con le nuove regole (consuma quota Gemini).
