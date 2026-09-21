# TrovAI · Next.js

Interfaccia Next.js di TrovAI. Sostituisce la UI Streamlit (`../awin_app5.py`) mantenendo la
stessa logica: Gemini estrae i filtri, SQLite restituisce i prodotti, il ranking è locale.

## Avvio

```bash
cp .env.example .env.local   # inserisci GEMINI_API_KEY e i dati del sito
npm install
npm run dev                  # http://localhost:3000
```

L'app legge lo stesso `../shop_database.db` della versione Python (percorso configurabile con
`DATABASE_PATH`, relativo alla cartella `TrovAI/`). Gli script Python `awin_db.py` e
`awin_feed_sync.py` continuano a popolare il database senza modifiche.

`GET /api/health` verifica chiave Gemini, database e prodotti attivi senza mostrare segreti.

## Struttura

| Percorso | Contenuto |
| --- | --- |
| `src/app/page.tsx` | Ricerca in chat con griglia prodotti |
| `src/app/{come-funziona,trasparenza,privacy,termini,contatti}` | Pagine informative |
| `src/app/api/search` | Sanitizzazione, rate limit (8/min per IP), ricerca |
| `src/app/api/feedback` | Feedback anonimo sui risultati |
| `src/lib/server/` | Porting di `src/*.py`: gemini, catalog (SQL), ranking, security, awin, feedback |
| `src/lib/disclosures.ts` | Testi di trasparenza (da `src/disclosures.py`) |
| `src/components/` | UI client: chat, card prodotto, filtri, preferiti e carrello |

Chat, preferiti e carrello restano nel `sessionStorage` del browser, come descritto
nell'informativa privacy. La cronologia inviata a Gemini contiene solo i filtri strutturati
ammessi, mai il testo originale.
