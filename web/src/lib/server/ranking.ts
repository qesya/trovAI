import "server-only";
import type { Filters } from "../types";

// Ranking deterministico e spiegabile (porting di src/ranking.py).

const STOPWORDS = new Set([
  "a", "al", "con", "da", "del", "di", "e", "in", "il", "la", "o", "per", "un", "una",
]);

type Row = Record<string, unknown>;

export interface RankedProduct {
  position: number;
  score: number;
  reasons: string[];
}

export function normalize(value: unknown): string {
  if (value == null) return "";
  return String(value)
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function splitValues(value: unknown): string[] {
  if (value == null) return [];
  return String(value)
    .split(/,|\s+(?:e|o)\s+/i)
    .map(normalize)
    .filter(Boolean);
}

function contains(haystack: unknown, needle: unknown): boolean {
  const n = normalize(needle);
  return Boolean(n) && normalize(haystack).includes(n);
}

function multiMatch(productValue: unknown, requested: unknown, logic: unknown): boolean {
  const values = splitValues(requested);
  if (!values.length) return false;
  const matches = values.map((v) => contains(productValue, v));
  return String(logic ?? "OR").toUpperCase() === "AND"
    ? matches.every(Boolean)
    : matches.some(Boolean);
}

export function rankProducts(products: Row[], filters: Filters): RankedProduct[] {
  const ranked = products.map((product, position) => {
    let score = 0;
    const reasons: string[] = [];

    if (filters.brand && contains(product.brand, filters.brand)) {
      score += 30;
      reasons.push(`marca ${product.brand}`);
    }

    const searchableCategory = ["product_type", "sottocategoria", "title"]
      .map((f) => String(product[f] ?? ""))
      .join(" ");
    if (filters.sottocategoria && contains(searchableCategory, filters.sottocategoria)) {
      score += 35;
      reasons.push(`categoria ${product.sottocategoria}`);
    } else if (filters.product_type && contains(searchableCategory, filters.product_type)) {
      score += 20;
      reasons.push(`tipologia ${product.product_type}`);
    }

    if (filters.color && multiMatch(product.color, filters.color, filters.color_logic)) {
      score += 15;
      reasons.push(`colore ${product.color}`);
    }

    if (
      filters.material &&
      multiMatch(product.material, filters.material, filters.material_logic)
    ) {
      score += 10;
      reasons.push(`materiale ${product.material}`);
    }

    const weighted: [keyof Filters, number, string][] = [
      ["gender", 8, "genere"],
      ["size", 8, "taglia"],
      ["merchant", 8, "negozio"],
      ["condizione", 5, "condizione"],
    ];
    for (const [field, points, label] of weighted) {
      if (filters[field] && contains(product[field], filters[field])) {
        score += points;
        reasons.push(`${label} ${product[field]}`);
      }
    }

    const keywords = normalize(filters.search_keywords)
      .split(" ")
      .filter((w) => w.length > 2 && !STOPWORDS.has(w));
    const searchableText = ["title", "description", "product_type", "sottocategoria"]
      .map((f) => normalize(product[f]))
      .join(" ");
    const keywordMatches = keywords.filter((w) => searchableText.includes(w)).length;
    if (keywordMatches) {
      score += Math.min(keywordMatches * 4, 20);
      reasons.push(`${keywordMatches} parole chiave pertinenti`);
    }

    return {
      position,
      score,
      reasons: reasons.length ? reasons.slice(0, 3) : ["corrisponde ai filtri applicati"],
    };
  });

  return ranked.sort((a, b) => b.score - a.score || a.position - b.position);
}
