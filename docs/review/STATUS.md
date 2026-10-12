# Verifica PR e hosting — 12 ottobre 2026

## Misurato

- PR #4 e #5 aperte; CI verde sui commit originali 4321737 e d55f4aa.
- Ramo locale `codex/hosting-streamlit-cleanup`: integra la correzione dei feed reali,
  rimuove il caricamento Streamlit/TOML, documenta Supabase e corregge il recupero
  dei job IA abbandonati.
- PostgreSQL 16 dedicato: **118 test passati**, ruff verde.
- Web: installazione da lockfile, lint, TypeScript e build di produzione riusciti.
- Smoke test: cinque offerte demo; ricerca con risultati di due merchant.
  Gemini non configurato intenzionalmente: verificato il fallback per parole chiave.
- `npm audit`: otto dipendenze segnalate (sette high, una critical), inclusa Next.js
  16.3.5. Dettagli in `dependency-audit.json`; nessun aggiornamento automatico applicato.
- Push e merge respinti da GitHub con 403. L'account attivo
  `PP-Immersive-Interactive` ha `push: false`; anche il connector non puo' unire PR.
  Nessuna modifica remota e nessun merge eseguito.

## Da completare

- Pubblicazione del ramo: n/a — manca accesso GitHub in scrittura.
- CI sui nuovi commit: n/a — push respinto.
- Merge: n/a — accesso in scrittura mancante; rieseguire i controlli sui commit pubblicati.
- Account/database Supabase: n/a — non configurato; nessun dato reale importato.
- Host Next.js: n/a — piano da confermare, Hobby Vercel non adatto all'uso commerciale.
- Valutare e correggere le dipendenze vulnerabili prima della pubblicazione.

Dopo aver ottenuto l'accesso: pubblicare i commit sul ramo PR #5, verificare CI,
integrare #4 e retargettare #5 su main prima del suo merge. Il PR deve descrivere
anche la migrazione della configurazione da TOML a `.env`.
