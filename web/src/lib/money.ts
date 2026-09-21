const SYMBOLS: Record<string, string> = { EUR: "€", GBP: "£", USD: "$" };

export function formatPrice(amount: number, currency = "EUR"): string {
  const code = (currency || "EUR").toUpperCase();
  const symbol = SYMBOLS[code];
  const value = Number(amount).toFixed(2);
  return symbol ? `${symbol}${value}` : `${value} ${code}`;
}

/** Prezzo effettivo: saldo solo se valido e inferiore al prezzo pieno. */
export function effectivePrice(price: number, salePrice: number | null): number {
  return salePrice != null && salePrice > 0 && salePrice < price ? salePrice : price;
}
