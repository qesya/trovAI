# Verifica PR e hosting — 12 ottobre 2026

## Misurato

- Il ramo `codex/hosting-streamlit-cleanup` integra la correzione dei feed reali,
  rimuove il caricamento Streamlit/TOML, documenta Supabase e corregge il recupero
  dei job IA abbandonati.
- PostgreSQL 16 dedicato: **118 test passati**, ruff verde.
- Web aggiornato a Next.js / eslint-config-next **16.3.8**: lint, TypeScript e
  build di produzione riusciti; sharp e source-map-js aggiornati nel lockfile.
- Smoke test prima delle patch alle dipendenze: cinque offerte demo; ricerca
  con risultati di due merchant. Gemini volutamente non configurato: verificato
  il fallback per parole chiave. La CI ripete lo smoke test sul ramo pubblicato.
- Audit produzione (`npm audit --omit=dev`): **zero vulnerabilita'**.
- Audit completo: **cinque segnalazioni high**, tutte nella catena di sviluppo
  ESLint/braces; dettagli e criteri di completamento in `tooling-followup.md`.
- Autenticazione personale `qesya` verificata con accesso amministrativo al repo.
  Git usa il profilo personale solo in TrovAI; il profilo globale resta separato.

## Stato di rilascio

- Pubblicazione/CI/merge: in corso; verificare lo stato aggiornato su GitHub PR #4 e #5.
- Supabase: n/a — progetto remoto non configurato; nessun dato reale importato.
- Host Next.js: n/a — piano da confermare, Hobby Vercel non adatto all'uso commerciale.
- Revisione dipendenze di sviluppo: aperta; nessun downgrade automatico applicato.

Il caricamento TOML storico e' rimosso: migrare le impostazioni in `.env` o nelle
variabili d'ambiente prima del deploy. La guida `docs/HOSTING.md` distingue le
connessioni di sessione della pipeline dal pooler per le API serverless.
