L'audit completo segnala GHSA-vfj7-8cjw-p6xm in `braces <=3.0.3`, transitivo della catena `eslint-config-next -> @next/eslint-plugin-next -> fast-glob -> micromatch -> braces`. Sono cinque pacchetti segnalati dalla stessa catena di sviluppo; `npm audit --omit=dev` restituisce zero vulnerabilita'.

Il registro npm indica ancora 3.0.3 come ultima versione di braces. Il fix automatico proposto dall'audit retrocede eslint-config-next a 14.2.35, incompatibile con la versione Next.js 16 del progetto: non applicarlo senza valutazione.

Criteri di completamento:
- Aggiornare la catena a una correzione compatibile oppure sostituire il componente vulnerabile con una soluzione verificata.
- `npm audit` senza questa segnalazione, lint, TypeScript e build verdi.
- Aggiornare i report in docs/review e la versione del lint plugin insieme a Next.js se necessario.

Evidenza: docs/review/dependency-audit.json; audit del 12 ottobre 2026. Gli advisory runtime di Next.js, sharp e source-map-js sono stati corretti nel ramo della PR #5.
