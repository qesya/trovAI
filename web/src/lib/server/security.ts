import "server-only";
import type { Filters } from "../types";

export class InputValidationError extends Error {}

const HISTORY_ALLOWED_KEYS = new Set([
  "age_group",
  "brand",
  "color",
  "color_logic",
  "condizione",
  "excluded_color",
  "excluded_material",
  "excluded_product_type",
  "gender",
  "in_stock_only",
  "material",
  "material_logic",
  "max_price",
  "merchant",
  "min_price",
  "only_on_sale",
  "product_type",
  "size",
  "sottocategoria",
  "sort_by",
]);

/** Rimuove caratteri di controllo e limita la dimensione inviata al modello. */
export function sanitizeQuery(value: unknown, maxLength = 500): string {
  const cleaned = String(value ?? "").replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, "").trim();
  if (!cleaned) throw new InputValidationError("Inserisci una richiesta non vuota.");
  if (cleaned.length > maxLength) {
    throw new InputValidationError(
      `La richiesta è troppo lunga. Usa al massimo ${maxLength} caratteri.`,
    );
  }
  return cleaned;
}

// Limite in memoria per client: 8 ricerche in 60 secondi, come nella versione Streamlit.
// Non sostituisce un limite applicato da reverse proxy, CDN o piattaforma di hosting.
const requestLog = new Map<string, number[]>();

export function checkRateLimit(
  clientKey: string,
  now = Date.now(),
  maxRequests = 8,
  windowMs = 60_000,
): boolean {
  const recent = (requestLog.get(clientKey) ?? []).filter((t) => now - t < windowMs);
  if (recent.length >= maxRequests) {
    requestLog.set(clientKey, recent);
    return false;
  }
  recent.push(now);
  requestLog.set(clientKey, recent);
  if (requestLog.size > 10_000) {
    for (const [key, times] of requestLog) {
      if (!times.some((t) => now - t < windowMs)) requestLog.delete(key);
    }
  }
  return true;
}

function minimize(filters: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(filters)
      .filter(([key, value]) => HISTORY_ALLOWED_KEYS.has(key) && value != null)
      .sort(([a], [b]) => a.localeCompare(b)),
  );
}

/** Conserva solo campi strutturati ammessi, escludendo testo e keyword libere. */
export function minimizeFilters(filters: Filters): Record<string, unknown> {
  const minimized = minimize(filters as Record<string, unknown>);
  if (Array.isArray(filters.sub_queries)) {
    const subs = filters.sub_queries
      .filter((sub) => sub && typeof sub === "object")
      .map((sub) => minimize(sub as Record<string, unknown>));
    if (subs.length) minimized.sub_queries = subs;
  }
  return minimized;
}

/** Ricostruisce la cronologia per il modello a partire dai soli filtri precedenti. */
export function buildFilterHistory(previous: unknown, maxChars = 1000): string {
  if (!Array.isArray(previous)) return "";
  const text = previous
    .filter((f) => f && typeof f === "object")
    .map((f) => `Filtri precedenti: ${JSON.stringify(minimizeFilters(f as Filters))}`)
    .join("\n");
  return text.slice(-maxChars);
}
