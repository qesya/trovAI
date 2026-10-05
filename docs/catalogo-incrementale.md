# Aggiornamento incrementale del catalogo

A ogni importazione (`trovai-sync --apply`, ogni notte dal workflow *Aggiorna
catalogo*) si aggiorna solo ciò che è cambiato. L'IA riceve soltanto prodotti
nuovi o con contenuti modificati, e mai due volte lo stesso contenuto.

## Cosa è stato riusato e cosa è nuovo (Task 1)

| Passaggio | Stato | Dove |
|---|---|---|
| Download completo prima dell'elaborazione, 3 tentativi | **riusato** | `awin_sync.download_rows` |
| Pulizia con regole (marca, categoria, colore, taglia…) senza IA | **riusato** | `feed_cleaner.clean_row` |
| Cache IA per impronta del contenuto | **riusata**, estesa | `feed_enrichment_cache` |
| Schema prodotto → colorazione → variante (EAN unico) → offerta per negozio | **riusato**, esteso | `normalized_catalog.py` |
| Registro delle importazioni | **riusato**, esteso | `feed_import_runs` |
| Impronta operativa separata da quella dei contenuti | nuovo | `CleanProduct.operational_hash` |
| Classificazione prima dell'IA | nuovo | `incremental.classify` |
| Aggiornamento dei soli campi operativi | nuovo | `incremental.update_operational` |
| Disattivazione senza cancellare, riattivazione | nuovo (prima: `DELETE`) | `normalized_catalog`, `incremental` |
| Protezione dai feed parziali/troncati | nuovo | `awin_sync._deactivate_missing` |
| Stato delle elaborazioni IA, presa in carico atomica | nuovo | `feed_ai_jobs`, `incremental.claim_ai_jobs` |
| Una sola importazione alla volta | nuovo | lock PostgreSQL (`pg_try_advisory_lock`) |
| Metriche, token, costo, stato `success`/`partial`/`failed` | nuovo | `feed_import_runs`, riepilogo del workflow |

## Identità (Task 2), senza IA

- **Offerta** = negozio + EAN se l'EAN è valido (controllo della cifra di
  verifica), altrimenti negozio + ID prodotto del negozio. Prezzo e
  disponibilità appartengono all'offerta: due negozi non si sovrascrivono.
- **Variante** = EAN quando c'è (taglia e colore diversi hanno EAN diversi);
  senza EAN, prodotto + colorazione + taglia + materiale.
- Un EAN che compare in seguito **completa** l'offerta e la variante esistenti
  invece di crearne di nuove.
- Righe tecniche ripetute nello stesso feed (stesso negozio e stesso EAN/ID):
  vale la prima, le altre vengono contate come `duplicates`.

## Classificazione (Task 3)

Ogni riga viene confrontata con l'offerta salvata **prima di qualsiasi chiamata IA**:

| Classe | Regola | Cosa succede |
|---|---|---|
| `new` | offerta mai vista | IA (se serve) + inserimento |
| `unchanged` | stesse impronte, offerta attiva | si aggiorna solo "visto in questa importazione" |
| `updated` | cambia solo l'impronta operativa | aggiornamento diretto, **zero IA** |
| `reactivated` | era esaurita ed è tornata | riattivazione, **zero IA**, dati IA intatti |
| `content` | cambia l'impronta dei contenuti | IA (se serve) + aggiornamento |

**Impronta dei contenuti** (decide se serve l'IA): versione delle regole di
normalizzazione, titolo originale, descrizione, marca, categoria del negozio,
colore, materiale, genere.

**Impronta operativa** (mai IA): prezzo, prezzo scontato, taglia, EAN, valuta,
nome del negozio, link, immagine.

Regola esplicita sulle **immagini**: la revisione testuale con Gemini non usa
l'immagine, quindi un'immagine nuova si aggiorna senza IA. I tag visivi
(`trovai-pipeline`) hanno un proprio passaggio.

## Campi operativi e arricchimenti (Task 4)

- `updated`/`reactivated` scrivono solo prezzo, disponibilità, taglia, link,
  immagine ed EAN; marca, categoria, colore, titolo del modello restano come sono.
- Anche nel percorso `content` un valore vuoto non cancella mai un valore già
  presente (`COALESCE` su tutti gli attributi arricchiti).
- La taglia del feed vince su quella in cache: l'IA la completa solo se manca.

## Esauriti, rimossi e feed parziali (Task 5)

- Niente `DELETE`: un'offerta esaurita o assente diventa `availability = false`
  (con `unavailable_since`) ed esce dai risultati acquistabili; i dati IA restano.
- Le assenze si valutano **solo** dopo un'importazione letta fino in fondo:
  un gzip troncato o un CSV illeggibile interrompe tutto (`failed`) prima di
  quel passo.
- Feed vuoto, oppure più del 50% di righe non valide: nessuna disattivazione.
- Per ogni negozio: se mancano almeno 20 offerte **e** più del 30% di quelle
  attive, la disattivazione viene sospesa e l'importazione chiusa come
  `partial` con un avviso (`--max-missing-ratio` per cambiare la soglia).
- Negozi assenti dal feed: non vengono toccati.

## Elaborazioni IA (Task 6)

- `feed_ai_jobs` registra per ogni impronta: stato (`pending`, `running`,
  `done`, `failed`), tentativi, ultimo errore, modello, versione delle regole,
  token.
- Prima della chiamata l'impronta viene **presa in carico** in modo atomico: due
  processi non la elaborano entrambi. Un `running` più vecchio di 30 minuti
  è considerato abbandonato.
- Righe con lo stesso contenuto (es. più taglie dello stesso articolo) vengono
  inviate una sola volta.
- I risultati si salvano **blocco per blocco**: un errore a metà non fa perdere
  il lavoro già fatto.
- Prodotti rimasti senza IA (budget `--ai-limit` esaurito, chiave mancante,
  errore) vengono ripresi alle importazioni successive, fino a 3 tentativi.
  `trovai-sync --apply --retry-ai-failures` rimette in coda quelli esauriti.

## Monitoraggio (Task 7)

`feed_import_runs` registra per ogni importazione: righe lette, nuovi,
invariati, aggiornati, contenuti modificati, riattivati, disattivati, duplicati,
inviati all'IA, risolti dalla cache, in attesa, errori IA, token in ingresso e
uscita, costo stimato (se sono impostati `GEMINI_INPUT_PRICE_PER_MTOK` e
`GEMINI_OUTPUT_PRICE_PER_MTOK`), stato, errore e avvisi. Su GitHub Actions lo
stesso riepilogo compare nella pagina dell'esecuzione.

## Test di accettazione (Task 7/8)

`pipeline/tests/test_incremental_sync.py` (PostgreSQL reale, Gemini finto che
conta le chiamate):

1. reimportazione dello stesso catalogo → 0 chiamate IA;
2. prezzo e taglie modificati → aggiornati, 0 chiamate IA, arricchimenti conservati;
3. nuovi prodotti → IA solo per i nuovi;
4. esaurito → riassortito → disattivato e riattivato senza perdere i dati IA;
5. feed parziale → nessuna disattivazione (stato `partial`); gzip troncato → `failed`, nessuna disattivazione;
6. errore IA a metà → al rilancio solo i falliti; budget esaurito → ripresi dopo;
7. identità: EAN/varianti/negozi/duplicati, EAN aggiunto in seguito;
8. importazioni contemporanee bloccate; presa in carico IA una sola volta.

## Nota sul primo rilascio

L'impronta dei contenuti è cambiata (la taglia ne è uscita), quindi alla prima
importazione dopo l'aggiornamento i prodotti che richiedono l'IA non trovano la
vecchia cache e vengono rielaborati una volta, entro `--ai-limit`. Su Neon il
catalogo è ancora vuoto, quindi non cambia nulla.
