import "server-only";
import type { Filters } from "../types";
import { getDb } from "./db";

// Porting fedele di query_ecommerce_catalog (awin_app5.py).

export interface CatalogRow {
  id: number;
  sku: string;
  title: string;
  description: string | null;
  brand: string | null;
  product_type: string | null;
  sottocategoria: string | null;
  gender: string | null;
  age_group: string | null;
  color: string | null;
  size: string | null;
  material: string | null;
  price: number;
  sale_price: number | null;
  availability: number;
  condizione: string | null;
  merchant: string;
  image_link: string | null;
  merchant_deep_link: string | null;
  advertiser_id: number | null;
  merchant_product_id: string | null;
  aw_deep_link: string | null;
  currency: string | null;
  source: string;
  source_updated_at: string | null;
}

const EFFECTIVE_PRICE =
  "(CASE WHEN sale_price IS NOT NULL AND sale_price > 0 THEN sale_price ELSE price END)";

/** Riduce il termine alla radice (es. "nera" -> "ner") per coprire le varianti di genere. */
function stem(value: string): string {
  const lower = value.toLowerCase();
  return lower.length > 3 ? lower.replace(/[aeiou]+$/, "") : lower;
}

function splitList(raw: string): string[] {
  return raw
    .replaceAll(" e ", ",")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function queryCatalog(filters: Filters, limit = 20, offset = 0): CatalogRow[] {
  const clauses: string[] = [];
  const params: (string | number)[] = [];
  const add = (clause: string, ...values: (string | number)[]) => {
    clauses.push(clause);
    params.push(...values);
  };
  const like = (v: unknown) => `%${v}%`;

  if (filters.gender) add("gender = ?", filters.gender);
  if (filters.age_group) add("age_group = ?", filters.age_group);
  if (filters.brand) add("brand LIKE ?", like(filters.brand));
  if (filters.merchant) add("merchant LIKE ?", like(filters.merchant));
  if (filters.condizione) add("condizione = ?", filters.condizione);

  if (filters.material) {
    const mats = splitList(filters.material);
    if (mats.length) {
      const joiner = (filters.material_logic ?? "AND").toUpperCase() === "AND" ? " AND " : " OR ";
      add(
        `(${mats.map(() => "LOWER(material) LIKE ?").join(joiner)})`,
        ...mats.map((m) => like(stem(m))),
      );
    }
  }

  if (filters.unwanted_features) {
    for (const feat of filters.unwanted_features.split(",").map((f) => f.trim())) {
      if (feat) add("title NOT LIKE ? AND description NOT LIKE ?", like(feat), like(feat));
    }
  }

  if (Array.isArray(filters.product_types_list) && filters.product_types_list.length) {
    const parts = filters.product_types_list.map(
      () => "(product_type LIKE ? OR sottocategoria LIKE ? OR title LIKE ?)",
    );
    add(
      `(${parts.join(" OR ")})`,
      ...filters.product_types_list.flatMap((pt) => [like(pt), like(pt), like(pt)]),
    );
  } else if (filters.product_type) {
    const t = like(filters.product_type);
    add("(product_type LIKE ? OR sottocategoria LIKE ? OR title LIKE ?)", t, t, t);
  }

  if (filters.sottocategoria) {
    const t = like(filters.sottocategoria);
    add("(sottocategoria LIKE ? OR title LIKE ?)", t, t);
  }

  if (filters.search_keywords) {
    const keywords = filters.search_keywords.replaceAll(",", " ").split(/\s+/).filter(Boolean);
    if (keywords.length) {
      add(
        `(${keywords
          .map(
            () =>
              "(title LIKE ? OR description LIKE ? OR product_type LIKE ? OR sottocategoria LIKE ?)",
          )
          .join(" OR ")})`,
        ...keywords.flatMap((kw) => Array(4).fill(like(kw))),
      );
    }
  }

  if (filters.excluded_color) {
    add("(LOWER(color) NOT LIKE ? OR color IS NULL)", like(stem(filters.excluded_color.trim())));
  }

  if (filters.color) {
    const colors = splitList(filters.color);
    if (colors.length) {
      const joiner = (filters.color_logic ?? "AND").toUpperCase() === "AND" ? " AND " : " OR ";
      add(
        `(${colors.map(() => "LOWER(color) LIKE ?").join(joiner)})`,
        ...colors.map((c) => like(stem(c))),
      );
    }
  }

  if (filters.size) add("size LIKE ?", like(filters.size));
  if (filters.max_price != null) add(`${EFFECTIVE_PRICE} <= ?`, Number(filters.max_price));
  if (filters.min_price) add(`${EFFECTIVE_PRICE} >= ?`, Number(filters.min_price));
  if (filters.only_on_sale === true) add("sale_price IS NOT NULL AND sale_price < price");
  if (filters.in_stock_only === true) add("availability = 1");

  if (filters.excluded_material) {
    add("(material NOT LIKE ? OR material IS NULL)", like(filters.excluded_material));
  }
  if (filters.excluded_product_type) {
    const t = like(filters.excluded_product_type);
    add("product_type NOT LIKE ? AND title NOT LIKE ?", t, t);
  }

  const orderBy =
    filters.sort_by === "price_asc"
      ? "COALESCE(sale_price, price) ASC"
      : filters.sort_by === "price_desc"
        ? "COALESCE(sale_price, price) DESC"
        : "id ASC";

  const where = clauses.length ? `WHERE ${clauses.join(" AND ")}` : "";
  const sql = `
    SELECT id, sku, title, description, brand, product_type, sottocategoria,
           gender, age_group, color, size, material, price, sale_price,
           availability, condizione, merchant, image_link, merchant_deep_link,
           advertiser_id, merchant_product_id, aw_deep_link, currency, source,
           source_updated_at
    FROM prodotti ${where}
    ORDER BY ${orderBy}
    LIMIT ? OFFSET ?`;

  return getDb()
    .prepare(sql)
    .all(...params, limit, offset) as CatalogRow[];
}
