import "server-only";
import type { Filters, ManualFilters, ProductResult, SearchResponse } from "../types";
import { resolveProductLink } from "./awin";
import { queryCatalog, type CatalogRow } from "./catalog";
import { flag } from "./config";
import { extractFilters } from "./gemini";
import { rankProducts } from "./ranking";

// Orchestrazione della ricerca: Gemini -> SQL -> ranking locale -> link (come in awin_app5.py).

export const MAX_PRICE_SLIDER = 250;

function applyManualFilters(filters: Filters, manual?: ManualFilters): Filters {
  const result = { ...filters };
  if (!manual) return result;
  if (manual.merchant && manual.merchant !== "Tutti") result.merchant = manual.merchant;
  if (manual.gender && manual.gender !== "Tutti") result.gender = manual.gender;
  if (manual.size && manual.size !== "Tutte") result.size = manual.size;
  if (manual.maxPrice < MAX_PRICE_SLIDER) result.max_price = Number(manual.maxPrice);
  if (manual.onSale) result.only_on_sale = true;
  return result;
}

function clean(filters: Filters): Filters {
  return Object.fromEntries(
    Object.entries(filters).filter(([k, v]) => k !== "sub_queries" && v != null),
  ) as Filters;
}

interface Scored {
  row: CatalogRow;
  score: number;
  reasons: string[];
}

function queryAndRank(filters: Filters, limit: number): Scored[] {
  const rows = queryCatalog(filters, limit, 0);
  return rankProducts(rows as unknown as Record<string, unknown>[], filters).map((r) => ({
    row: rows[r.position],
    score: r.score,
    reasons: r.reasons,
  }));
}

function responseMessage(count: number): string {
  if (count === 0) {
    return (
      "Non ho trovato articoli che rispettino tutti i filtri. " +
      "Prova a rimuoverne uno o ad ampliare la fascia di prezzo."
    );
  }
  if (count === 1) return "Ho trovato 1 articolo compatibile con i filtri applicati.";
  return `Ho trovato ${count} articoli compatibili, ordinati per pertinenza.`;
}

export async function runSearch(
  query: string,
  history: string,
  manual?: ManualFilters,
): Promise<SearchResponse> {
  let filtersData = await extractFilters(query, history);
  if (!filtersData || !Object.keys(filtersData).length) {
    console.warn("Estrazione AI non disponibile: applicato fallback per parole chiave");
    filtersData = { search_keywords: query, in_stock_only: true };
  }

  const results: Scored[] = [];
  let appliedFilters: Filters;
  const subQueries = filtersData.sub_queries;

  if (Array.isArray(subQueries) && subQueries.length) {
    for (const sub of subQueries) {
      const subFilters = clean(applyManualFilters(sub, manual));
      if (Object.keys(subFilters).length) results.push(...queryAndRank(subFilters, 15));
    }
    appliedFilters = filtersData;
  } else {
    appliedFilters = applyManualFilters(filtersData, manual);
    results.push(...queryAndRank(clean(appliedFilters), 30));
  }

  // Unione: ordinamento stabile per punteggio e rimozione dei duplicati.
  const seen = new Set<number>();
  const merged = results
    .map((item, index) => ({ item, index }))
    .sort((a, b) => b.item.score - a.item.score || a.index - b.index)
    .map(({ item }) => item)
    .filter(({ row }) => (seen.has(row.id) ? false : (seen.add(row.id), true)));

  const products: ProductResult[] = await Promise.all(
    merged.map(async ({ row, score, reasons }, idx) => ({
      id: row.id,
      title: row.title,
      description: row.description,
      brand: row.brand,
      product_type: row.product_type,
      sottocategoria: row.sottocategoria,
      gender: row.gender,
      color: row.color,
      size: row.size,
      material: row.material,
      price: Number(row.price),
      sale_price: row.sale_price == null ? null : Number(row.sale_price),
      currency: row.currency || "EUR",
      merchant: row.merchant,
      image_link: row.image_link,
      source: row.source,
      source_updated_at: row.source_updated_at,
      link: await resolveProductLink(row, idx + 1),
      score,
      reasons,
    })),
  );

  return {
    message: responseMessage(products.length),
    products,
    filters: appliedFilters,
    ...(flag("APP_DEBUG") ? { debugFilters: appliedFilters } : {}),
  };
}
