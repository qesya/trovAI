import "server-only";
import { Pool, types, type QueryResultRow } from "pg";
import { getSetting } from "./config";

// PostgreSQL restituisce NUMERIC e BIGINT come stringhe: prezzi e ID servono come numeri.
types.setTypeParser(types.builtins.NUMERIC, (value) => Number.parseFloat(value));
types.setTypeParser(types.builtins.INT8, (value) => Number.parseInt(value, 10));

let pool: Pool | null = null;

/**
 * Connessione condivisa allo stesso PostgreSQL in cui scrive la pipeline (pipeline/).
 * Accetta DATABASE_URL oppure le stesse variabili POSTGRES_* della pipeline.
 */
export function getPool(): Pool {
  if (!pool) {
    const connectionString = getSetting("DATABASE_URL");
    pool = connectionString
      ? new Pool({ connectionString, max: 5 })
      : new Pool({
          host: getSetting("POSTGRES_HOST", "localhost"),
          port: Number(getSetting("POSTGRES_PORT", "5432")),
          database: getSetting("POSTGRES_DATABASE", "TrovAI"),
          user: getSetting("POSTGRES_USER"),
          password: getSetting("POSTGRES_PASSWORD"),
          max: 5,
        });
  }
  return pool;
}

/** Converte i segnaposto `?` in `$1, $2, ...`: le query restano leggibili come prima. */
export function toPositional(sql: string): string {
  let index = 0;
  return sql.replace(/\?/g, () => `$${++index}`);
}

export async function query<T extends QueryResultRow>(
  sql: string,
  params: readonly unknown[] = [],
): Promise<T[]> {
  const result = await getPool().query<T>(toPositional(sql), params as unknown[]);
  return result.rows;
}
