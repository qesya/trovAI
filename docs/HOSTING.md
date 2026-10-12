# Pubblicare TrovAI con Supabase

Configurazione proposta il 12 ottobre 2026. Nessun database o deploy remoto e'
stato creato o verificato da questo documento.

## Componenti

- **Database:** PostgreSQL su Supabase Free.
- **Sito e backend HTTP:** `web/`, Next.js e le sue API `/api/search`,
  `/api/feedback`, `/api/health`, su un host compatibile con Node.js.
- **Import:** workflow GitHub Actions `Aggiorna catalogo`, manuale e notturno.
  Python non richiede un servizio sempre acceso.

Supabase Free include 500 MB per database e puo' sospendere progetti con poca
attivita' per sette giorni. Non presumere che il catalogo rientri nella quota:
misura anche cache IA, indici e immagini elaborate dopo l'import iniziale.
Le chiamate Gemini e le quote del provider web restano separate.

## Connessioni

Crea un progetto Supabase Free nella regione scelta e apri **Connect**.
Copia le stringhe dal pannello; non ricostruire l'hostname dalla regione.
Codifica i caratteri speciali della password nell'URL e abilita SSL.

| Destinazione | Segreto `DATABASE_URL` |
|---|---|
| GitHub Actions / pipeline Python | **Session pooler**, porta **5432**, oppure connessione diretta se il runner supporta IPv6 |
| API Next.js su serverless | **Transaction pooler**, porta **6543** |
| Next.js su server Node permanente | Session pooler o connessione diretta compatibile con la rete |

La pipeline usa un advisory lock PostgreSQL di sessione attraverso piu' commit:
il Transaction pooler non e' adatto. Il client web `pg` non usa prepared statement
con nome. Non usare una chiave `anon` o `service_role` al posto della password SQL.
Mantieni tutte le credenziali nell'ambiente server, mai in `NEXT_PUBLIC_*`.

TrovAI usa SQL dal backend e non necessita della Data API di Supabase. Disabilita
la Data API prima di importare: le tabelle create via SQL non hanno policy RLS
configurate per un accesso diretto dal browser.

## Configurazione e primo import

1. Configura nei segreti GitHub Actions `DATABASE_URL` (sessione),
   `AWIN_FEED_DOWNLOAD_URL` e, se desiderato, `GEMINI_API_KEY`.
2. Avvia **Actions → Aggiorna catalogo → Run workflow** con `ai_limit=0`
   per verificare prima il feed senza costi Gemini. Lascia vuoti i parametri
   bootstrap ed evita `replace_catalog` su dati esistenti.
3. Controlla l'esito e `feed_import_runs`; verifica prezzi, taglie e disponibilita'.
4. Sul provider web imposta la root `web`, Node.js 22, `npm ci`,
   `npm run build` e, per un server Node, `npm run start`.
5. Imposta `DATABASE_URL` del web, `GEMINI_API_KEY`, `SITE_OWNER`,
   `CONTACT_EMAIL`, `PRIVACY_EMAIL` e le altre variabili di `web/.env.example`.
6. Verifica `/api/health` con `ok: true`, una ricerca e un link affiliato reale.
   Completa `PRODUCTION_CHECKLIST.md` e conserva le evidenze.

La precedente configurazione TOML non e' piu' supportata. Trasferisci i valori
in `.env` (pipeline), `.env.local` (web) o nei segreti dell'host prima del deploy.
Non copiare file di segreti nel repository.

## Hosting web e costi

La configurazione `web/vercel.json` mantiene la regione Francoforte. Vercel Hobby
consente solo uso personale non commerciale: un sito con attivita' affiliata
richiede un piano adatto o un altro host. Supabase ospita il database, non il
server Next.js. La scelta e l'attivazione dell'host web restano da confermare.

## Fonti

- [Prezzi Supabase](https://supabase.com/pricing)
- [Sospensione dei progetti gratuiti](https://supabase.com/docs/guides/platform/free-project-pausing)
- [Connessioni PostgreSQL e pooler](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Data API](https://supabase.com/docs/guides/api/securing-your-api)
- [Limiti Vercel Hobby](https://vercel.com/docs/plans/hobby)
