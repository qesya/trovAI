import { getSetting } from "@/lib/server/config";
import { query } from "@/lib/server/db";

// Verifica database e configurazioni obbligatorie senza esporre i valori dei segreti.
export async function GET() {
  const checks: Record<string, boolean> = {
    gemini_api_key_configured: Boolean(getSetting("GEMINI_API_KEY")),
    database_reachable: false,
    active_products: false,
  };
  let productCount = 0;
  try {
    const [row] = await query<{ n: number }>(
      "SELECT COUNT(*) AS n FROM catalog_search WHERE availability = 1",
    );
    productCount = row.n;
    checks.database_reachable = true;
    checks.active_products = productCount > 0;
  } catch {
    // il flag database_reachable resta false
  }
  const ok = Object.values(checks).every(Boolean);
  return Response.json({ ok, checks, productCount }, { status: ok ? 200 : 503 });
}
