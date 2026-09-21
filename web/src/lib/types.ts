export type Logic = "AND" | "OR";

/** Filtri strutturati estratti da Gemini o impostati manualmente. */
export interface Filters {
  brand?: string | null;
  product_type?: string | null;
  sottocategoria?: string | null;
  gender?: string | null;
  age_group?: string | null;
  color?: string | null;
  color_logic?: Logic | null;
  size?: string | null;
  material?: string | null;
  material_logic?: Logic | null;
  merchant?: string | null;
  condizione?: string | null;
  min_price?: number | null;
  max_price?: number | null;
  only_on_sale?: boolean | null;
  in_stock_only?: boolean | null;
  search_keywords?: string | null;
  excluded_color?: string | null;
  excluded_material?: string | null;
  excluded_product_type?: string | null;
  unwanted_features?: string | null;
  sort_by?: string | null;
  product_types_list?: string[] | null;
  sub_queries?: Filters[] | null;
}

/** Filtri rapidi della barra laterale. */
export interface ManualFilters {
  merchant: string;
  gender: string;
  size: string;
  maxPrice: number;
  onSale: boolean;
}

/** Prodotto restituito al client, con link gia risolto e motivazioni del ranking. */
export interface ProductResult {
  id: number;
  title: string;
  description: string | null;
  brand: string | null;
  product_type: string | null;
  sottocategoria: string | null;
  gender: string | null;
  color: string | null;
  size: string | null;
  material: string | null;
  price: number;
  sale_price: number | null;
  currency: string;
  merchant: string;
  image_link: string | null;
  source: string;
  source_updated_at: string | null;
  link: string;
  score: number;
  reasons: string[];
}

export interface SearchResponse {
  message: string;
  products: ProductResult[];
  filters: Filters;
  debugFilters?: Filters;
}

export interface SavedItem {
  id: number;
  title: string;
  brand: string | null;
  size: string | null;
  price: number;
  sale_price: number | null;
  currency: string;
}
