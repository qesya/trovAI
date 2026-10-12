# TrovAI e attribuzione delle vendite affiliate

Traccia per il confronto con il titolare di TrovAI e il referente Awin o del negozio, aggiornata al 12 ottobre 2026. TrovAI è un comparatore: l'utente sceglie un'offerta e acquista sul sito del partner. La lista prodotti non è un carrello e TrovAI non gestisce ordini o pagamenti. L'ambiente attuale è staging.

## Stato verificato nel codice

- `web/src/components/ProductCard.tsx` apre il link risolto dal backend. `SavedDrawer.tsx` conserva ora lo stesso URL nella lista, senza riscriverne i parametri. Le vecchie sessioni senza URL invitano a ripetere la ricerca.
- `web/src/lib/server/awin.ts`, funzione `resolveProductLink`, preferisce `aw_deep_link`, ma può ripiegare su `merchant_deep_link`. Questo fallback può inviare traffico non attribuibile: un URL di negozio non dimostra affiliazione.
- Nello stesso file, `buildClickParameters` prepara riferimenti per ricerca, prodotto e posizione. Vengono applicati soltanto nel percorso Link Builder abilitato e configurato; non basta che la funzione esista per avere report per prodotto.
- Il collaudo descritto nell'issue [12](https://github.com/qesya/trovAI/issues/12) non ha verificato una conversione. L'errore DNS osservato su un link Awin va riprovato da una rete indipendente; non dimostra un problema generalizzato del partner.

## Last click e consenso

Awin applica normalmente l'ultimo clic valido, con priorità dei clic standard e incentivati sui soft click e sulle visualizzazioni. Quindi non ogni estensione o contatto successivo sottrae automaticamente l'attribuzione. Le eccezioni per alcuni programmi cashback non rendono i cookie di un comparatore automaticamente necessari. [Gerarchia Awin](https://help.awin.com/advertisers/docs/en/awin-cookie-types-and-attribution-hierarchy).

La finestra di attribuzione e la deduplicazione fra canali vanno confermate per ogni programma. Non assumiamo una durata standard per Camden. Un clic, una vendita registrata e una commissione approvata sono risultati distinti. [FAQ di tracciamento Awin](https://help.awin.com/docs/tracking-faqs).

Il parametro `awc` identifica il clic per l'attribuzione; `clickref` permette di aggiungere riferimenti di campagna. Soltanto il primo clickref può essere inoltrato alla pagina del negozio. I riferimenti proposti devono descrivere ambiente, posizione e prodotto, senza email, dati personali o testo libero della ricerca. [Parametri Awin](https://help.awin.com/developers/docs/click-appends-dyn-params).

Sul negozio, Awin prevede segnali di consenso anche nelle integrazioni server. Un'implementazione server to server non va quindi considerata un'esenzione dal consenso. Per TrovAI occorre censire i trattamenti effettivi prima di scegliere eventuali script e gestione del consenso; la disclosure del link non sostituisce il consenso quando richiesto. [Consent Signals Awin](https://help.awin.com/developers/docs/gtm-consent), [linee guida del Garante](https://www.garanteprivacy.it/home/docweb/-/docweb-display/docweb/9677876), [elenco cookie Awin](https://privacy.awin.com/).

## Decisioni da prendere insieme

| Tema | Domanda concreta | Interlocutore e stato |
| --- | --- | --- |
| Programma iniziale | Camden è approvato per TrovAI e per questo dominio? Quali paesi, categorie, coupon e clienti sono ammessi? | Titolare e referente programma; n/a — condizioni non verificate |
| Attribuzione | Qual è la finestra? Come vengono trattati altri affiliati, PPC, codici sconto e ritorni diretti? | Referente programma; n/a — regole da ottenere |
| Implementazione del negozio | Il clic sopravvive a redirect, consenso, checkout e passaggio all'app? Sono presenti tracciamento server e segnali di consenso corretti? | Partner e supporto Awin; n/a — integrazione non collaudata |
| Dati di TrovAI | Quali clickref servono? Come separare staging e pubblico? Quali dati conservare e per quanto? | Titolare, sviluppo e consulente privacy; n/a — decisione aperta |
| Link non tracciabili | Nascondere l'offerta o mostrare un link diretto esplicitamente non affiliato? | Titolare; n/a — politica da scegliere prima di modificare il fallback |
| Ricavi reali | Commissioni, esclusioni, resi, annullamenti, tempi di validazione e procedura vendite mancanti? | Referente programma; n/a — condizioni da ottenere |

## Interventi proposti dopo il confronto

1. Verificare un piccolo campione di link e l'identità publisher/advertiser. Segnalare link mancanti o diretti; non nascondere gli errori dietro una promessa di tracciamento.
2. Definire clickref coerenti e verificare che compaiano nei report Awin. Separare i test dalle metriche pubbliche. Il conteggio dei clic in uscita, se introdotto, richiede una scelta esplicita su dati, conservazione e consenso.
3. Concordare con il partner test di conversione autorizzati: desktop e mobile, consenso accordato/rifiutato, ritorno successivo e passaggio all'app se pertinente. Nessun acquisto reale è incluso nel collaudo dell'app.
4. Confrontare per periodo e partner clic Awin, vendite in attesa, approvate/rifiutate e commissioni pagate. Usare coorti mature per evitare che i tempi di validazione falsino i risultati. EPC approvato = commissioni approvate / clic della stessa coorte; un clic senza vendita non è automaticamente una commissione persa.
5. Migliorare pertinenza, velocità, prezzo e disponibilità delle offerte; valutare eventuali accordi di attribuzione o commissione con il partner. Non promettere protezione assoluta dal last click e non forzare nuovi clic o cookie per sovrascrivere altri affiliati.

## Esito necessario prima di dichiarare pronto il tracciamento

Condizioni del programma confermate, decisione sul fallback, mappa dei dati e del consenso, clickref leggibili nei report e almeno un percorso di conversione concordato con esito verificabile. Il completamento delle correzioni dell'interfaccia non chiude questi punti.
