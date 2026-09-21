import "server-only";
import { createHash } from "node:crypto";
import type { CatalogRow } from "./catalog";
import { flag, getSetting, requireSetting } from "./config";
import { getDb } from "./db";

// Link Builder Awin con cache di 7 giorni nella tabella tracking_links
// (porting di src/awin_tracking.py e resolve_product_link).

const API_BASE_URL = "https://api.awin.com";
const TTL_MS = 7 * 24 * 60 * 60 * 1000;

export function buildClickParameters(productId: number, position: number, campaign: string) {
  return {
    campaign: campaign.slice(0, 50),
    clickref: "trovai-search",
    clickref2: `product-${productId}`,
    clickref3: `position-${position}`,
  };
}

function linkBuilderConfig() {
  if (!flag("AWIN_LINK_BUILDER_ENABLED")) return null;
  const publisherId = Number(requireSetting("AWIN_PUBLISHER_ID"));
  if (!Number.isInteger(publisherId)) {
    throw new Error("AWIN_PUBLISHER_ID deve essere un identificativo numerico valido.");
  }
  return {
    publisherId,
    token: requireSetting("AWIN_API_TOKEN"),
    campaign: getSetting("AWIN_TRACKING_CAMPAIGN", "trovai-search")!,
  };
}

// Ordina le chiavi come Python sorted(parameters.items()) per mantenere compatibili le chiavi di cache.
function cacheKey(advertiserId: number, destinationUrl: string, params: Record<string, string>) {
  const sorted = Object.fromEntries(Object.entries(params).sort(([a], [b]) => (a < b ? -1 : 1)));
  const canonical = JSON.stringify([advertiserId, destinationUrl, sorted]).replace(
    /[\u007f-\uffff]/g,
    (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"),
  );
  return createHash("sha256").update(canonical, "utf8").digest("hex");
}

function ensureCacheTable() {
  getDb().exec(`
    CREATE TABLE IF NOT EXISTS tracking_links (
      cache_key TEXT PRIMARY KEY,
      advertiser_id INTEGER NOT NULL,
      destination_url TEXT NOT NULL,
      tracking_url TEXT NOT NULL,
      parameters_json TEXT NOT NULL,
      created_at TEXT NOT NULL
    )`);
}

async function generateLink(
  publisherId: number,
  token: string,
  advertiserId: number,
  destinationUrl: string,
  parameters: Record<string, string>,
): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/publishers/${publisherId}/linkbuilder/generate`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      Accept: "application/json",
      "User-Agent": "TrovAI-Awin-Link-Builder/1.0",
    },
    body: JSON.stringify({ advertiserId, destinationUrl, parameters, shorten: false }),
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) throw new Error("Link Builder Awin non disponibile");
  const result = (await response.json()) as { url?: string };
  if (!result?.url) throw new Error("Awin non ha generato un tracking link");
  return String(result.url);
}

/** Restituisce un link Awin tracciato o il miglior fallback disponibile. */
export async function resolveProductLink(row: CatalogRow, position: number): Promise<string> {
  const awinLink = row.aw_deep_link?.trim();
  const merchantLink = row.merchant_deep_link?.trim();
  const fallback = awinLink || merchantLink || "#";

  let config;
  try {
    config = linkBuilderConfig();
  } catch (error) {
    console.error(String(error));
    return fallback;
  }
  if (!config || row.source !== "awin" || row.advertiser_id == null || !merchantLink) {
    return fallback;
  }

  const params = buildClickParameters(row.id, position, config.campaign);
  const key = cacheKey(row.advertiser_id, merchantLink, params);
  try {
    ensureCacheTable();
    const db = getDb();
    const cached = db
      .prepare("SELECT tracking_url, created_at FROM tracking_links WHERE cache_key = ?")
      .get(key) as { tracking_url: string; created_at: string } | undefined;
    if (cached) {
      const age = Date.now() - new Date(cached.created_at).getTime();
      if (Number.isFinite(age) && age <= TTL_MS) return cached.tracking_url;
      db.prepare("DELETE FROM tracking_links WHERE cache_key = ?").run(key);
    }

    const url = await generateLink(
      config.publisherId,
      config.token,
      row.advertiser_id,
      merchantLink,
      params,
    );
    db.prepare(
      `INSERT INTO tracking_links (cache_key, advertiser_id, destination_url, tracking_url,
         parameters_json, created_at) VALUES (?, ?, ?, ?, ?, ?)
       ON CONFLICT(cache_key) DO UPDATE SET
         tracking_url=excluded.tracking_url, created_at=excluded.created_at`,
    ).run(key, row.advertiser_id, merchantLink, url, JSON.stringify(params), new Date().toISOString().replace("Z", "+00:00"));
    return url;
  } catch (error) {
    console.error(`Impossibile generare il tracking link per advertiser ${row.advertiser_id}`, String(error));
    return fallback;
  }
}
