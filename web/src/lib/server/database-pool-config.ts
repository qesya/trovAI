import type { PoolConfig } from "pg";

/** Keep certificate and hostname verification enabled for provider-specific CAs. */
export function databasePoolConfig(connectionString: string, ca?: string): PoolConfig {
  const common = { max: 5, connectionTimeoutMillis: 10_000 };
  if (!ca) return { ...common, connectionString };

  // pg URL SSL options override the explicit ssl object, including its CA.
  const url = new URL(connectionString);
  for (const key of ["sslmode", "sslrootcert", "sslcert", "sslkey", "ssl", "uselibpqcompat"]) {
    url.searchParams.delete(key);
  }
  return {
    ...common,
    connectionString: url.toString(),
    ssl: { ca: ca.replace(/\\n/g, "\n"), rejectUnauthorized: true },
  };
}
