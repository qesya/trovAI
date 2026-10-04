# TrovAI · Next.js

Interfaccia Next.js di TrovAI: Gemini estrae i filtri, PostgreSQL restituisce i prodotti
(catalogo creato dalla pipeline in `../pipeline`), il ranking è locale.

## Avvio

```bash
cp .env.example .env.local   # inserisci GEMINI_API_KEY e i dati del sito
npm install
npm run dev                  # http://localhost:3000
```

L'app legge il catalogo dalla vista PostgreSQL `catalog_search`, creata e aggiornata dalla
pipeline (`../pipeline`): una riga per offerta di un negozio, solo quelle disponibili vengono
mostrate. Per avere dati in locale esegui prima un import, ad esempio
`trovai-sync --apply` dalla radice del repository (vedi `../pipeline/README.md`).

`GET /api/health` verifica chiave Gemini, database e offerte disponibili senza mostrare segreti.

## Struttura

| Percorso | Contenuto |
| --- | --- |
| `src/app/page.tsx` | Ricerca in chat con griglia prodotti |
| `src/app/{come-funziona,trasparenza,privacy,termini,contatti}` | Pagine informative |
| `src/app/api/search` | Sanitizzazione, rate limit (8/min per IP), ricerca |
| `src/app/api/feedback` | Feedback anonimo sui risultati |
| `src/lib/server/` | gemini, catalog (PostgreSQL), ranking, security, awin (link tracciati), feedback |
| `src/lib/disclosures.ts` | Testi di trasparenza |
| `src/components/` | UI client: chat, card prodotto, filtri, preferiti e carrello |

Chat, preferiti e carrello restano nel `sessionStorage` del browser, come descritto
nell'informativa privacy. La cronologia inviata a Gemini contiene solo i filtri strutturati
ammessi, mai il testo originale.
